"""本地演示入口，默认关闭，不提供真实账号的免登录访问。"""
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, model_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.teacher import Teacher
from app.schemas.user import TokenResponse, UserResponse
from app.services.auth import create_access_token
from app.services.debug_identity import demo_enabled, demo_user

router = APIRouter(prefix="/api/debug", tags=["本地演示"])


class DebugSessionRequest(BaseModel):
    role: Literal["admin", "teacher"]
    teacher_id: int | None = None

    @model_validator(mode="after")
    def validate_identity(self):
        if (self.role == "teacher") != (self.teacher_id is not None):
            raise ValueError("教师身份需要选择教师，管理员身份不接受教师ID")
        return self


def require_demo(request: Request):
    if not demo_enabled(request):
        raise HTTPException(status_code=404, detail="本地演示模式未启用")


@router.get("/status")
def debug_status(request: Request):
    return {"enabled": demo_enabled(request)}


@router.get("/identities", dependencies=[Depends(require_demo)])
def debug_identities(db: Session = Depends(get_db)):
    return {"teachers": [{"id": t.id, "name": t.name, "teacher_code": t.teacher_code}
                         for t in db.query(Teacher).order_by(Teacher.id).all()]}


@router.post("/session", response_model=TokenResponse, dependencies=[Depends(require_demo)])
def debug_session(data: DebugSessionRequest, db: Session = Depends(get_db)):
    user = demo_user(data.role, data.teacher_id, db)
    if user is None:
        raise HTTPException(status_code=404, detail="演示教师不存在")
    token = create_access_token({"sub": f"debug:{user.id}", "demo": True,
                                 "role": data.role, "teacher_id": data.teacher_id},
                                expires_delta=timedelta(minutes=30))
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user))
