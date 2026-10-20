"""认证服务 — 密码哈希、JWT 令牌管理、用户验证"""
import hashlib
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.services.debug_identity import demo_enabled, demo_user

# JWT 配置
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24小时


def _load_secret_key() -> str:
    """解析 JWT 签名密钥。

    - 设置了 SECRET_KEY 环境变量/配置项时直接使用；
    - 开发环境未配置时，在 backend/data/jwt_secret.key 生成并持久化随机密钥，
      避免进程重启后所有已签发令牌失效；
    - 非 DEBUG 环境未配置时直接失败，防止以可预测的默认密钥启动。
    """
    configured = (settings.SECRET_KEY or "").strip()
    if configured:
        return configured

    if not settings.DEBUG:
        raise RuntimeError(
            "SECRET_KEY 未配置：生产环境必须通过环境变量 SECRET_KEY 提供服务端签名密钥"
        )

    secret_path = Path(__file__).resolve().parents[2] / "data" / "jwt_secret.key"
    try:
        if secret_path.exists():
            value = secret_path.read_text(encoding="utf-8").strip()
            if value:
                return value

        value = secrets.token_urlsafe(48)
        secret_path.parent.mkdir(parents=True, exist_ok=True)
        secret_path.write_text(value, encoding="utf-8")
        try:
            secret_path.chmod(0o600)
        except OSError:
            pass
        return value
    except OSError:
        # 只读文件系统等情况下退回进程内随机密钥（重启后令牌失效，但不会泄露固定密钥）
        return secrets.token_urlsafe(48)


SECRET_KEY = _load_secret_key()

# HTTP Bearer 安全方案
security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """使用 PBKDF2-SHA256 对密码进行哈希"""
    salt = secrets.token_hex(16)
    pwd_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
    return f"{salt}${pwd_hash.hex()}"


def verify_password(plain_password: str, hashed: str) -> bool:
    """验证密码是否匹配"""
    try:
        salt, stored_hash = hashed.split("$", 1)
        computed_hash = hashlib.pbkdf2_hmac(
            "sha256", plain_password.encode("utf-8"), salt.encode("utf-8"), 100000
        )
        return computed_hash.hex() == stored_hash
    except (ValueError, AttributeError):
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """生成 JWT 访问令牌"""
    to_encode = data.copy()
    if "sub" in to_encode:
        to_encode["sub"] = str(to_encode["sub"])
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> Optional[dict]:
    """验证 JWT 令牌并返回载荷"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """从请求中获取当前登录用户（可选认证）"""
    if credentials is None:
        return None
    payload = verify_token(credentials.credentials)
    if payload is None:
        return None
    if payload.get("demo"):
        if not demo_enabled(request):
            return None
        return demo_user(payload.get("role"), payload.get("teacher_id"), db)
    user_id: int = payload.get("sub")
    if user_id is None:
        return None
    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        return None
    from app.models.planning import AccountGrant, TeacherBinding
    user.grants = [{'capability': g.capability, 'scope': g.scope, 'scope_id': g.scope_id}
                   for g in db.query(AccountGrant).filter_by(user_id=user.id)]
    binding = db.get(TeacherBinding, user.id)
    user.teacher_id = binding.teacher_id if binding else None
    return user


async def require_user(
    current_user: Optional[User] = Depends(get_current_user),
) -> User:
    """要求用户必须登录，否则返回 401"""
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录",
        )
    return current_user


async def require_management_access(current_user: User = Depends(require_user)) -> User:
    """拒绝教师访问旧管理接口；普通旧账号暂保留原有管理访问。"""
    from app.services.authorization import check
    check(current_user, 'admin')
    return current_user
