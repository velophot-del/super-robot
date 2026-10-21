"""用户认证 API 路由"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, AccountSetup
from app.schemas.user import UserRegister, UserLogin, UserResponse, TokenResponse, PasswordChange
from app.services.auth import hash_password, verify_password, require_user, load_account_access, account_token

router = APIRouter(prefix="/api/auth", tags=["用户认证"])


@router.post("/register", include_in_schema=False)
def register(data: UserRegister, db: Session = Depends(get_db)):
    """账号由管理员导入创建，关闭公开注册。"""
    raise HTTPException(403, '公开注册已关闭，请联系管理员导入教师名单')


@router.post("/login", response_model=TokenResponse)
def login(data: UserLogin, db: Session = Depends(get_db)):
    """用户登录"""
    # 查找用户
    user = db.query(User).filter(User.username == data.username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    # 验证密码
    if not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账户已被禁用")

    # 生成令牌
    load_account_access(user, db)
    access_token = account_token(user, db)

    return TokenResponse(
        access_token=access_token,
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(require_user)):
    """获取当前登录用户信息"""
    return UserResponse.model_validate(current_user)


@router.post('/password', response_model=TokenResponse)
def change_password(data: PasswordChange, user=Depends(require_user), db: Session=Depends(get_db)):
    if getattr(user, 'is_demo', False):
        raise HTTPException(403, '演示身份没有真实账号密码')
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(400, '当前密码不正确')
    if data.new_password == '123456' or verify_password(data.new_password, user.password_hash):
        raise HTTPException(422, '新密码不能与原密码或初始密码相同')
    setup = db.get(AccountSetup, user.id)
    if not setup:
        setup = AccountSetup(user_id=user.id, password_changed=True, token_version=0); db.add(setup)
    setup.password_changed = True; setup.token_version += 1
    user.password_hash = hash_password(data.new_password)
    db.commit(); load_account_access(user, db)
    return TokenResponse(access_token=account_token(user, db), user=UserResponse.model_validate(user))
