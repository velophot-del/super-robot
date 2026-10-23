"""显式启用、限定本机和独立数据库的演示身份，不创建真实用户。"""
from fastapi import Request
from sqlalchemy.orm import Session

from app.config import settings
from app.models.teacher import Teacher
from app.models.user import User


def demo_enabled(request: Request) -> bool:
    return bool(
        settings.DEBUG_DEMO_MODE
        and settings.DEBUG_DEMO_DATABASE_URL
        and settings.DEBUG_DEMO_DATABASE_URL == settings.DATABASE_URL
        and request.client
        and request.client.host in {"127.0.0.1", "::1"}
        and request.url.hostname in {"localhost", "127.0.0.1", "::1"}
    )


def demo_user(role: str, teacher_id: int | None, db: Session) -> User | None:
    if role == "teacher":
        teacher = db.get(Teacher, teacher_id) if teacher_id is not None else None
        if teacher is None:
            return None
        user = User(id=-1000 - teacher.id, username=teacher.name,
                    email="teacher@demo.invalid", is_active=True)
    elif role == "admin" and teacher_id is None:
        user = User(id=-1, username="演示管理员", email="admin@demo.invalid", is_active=True)
    else:
        return None
    user.role = role
    user.teacher_id = teacher_id
    user.is_demo = True
    user.grants = ([{'capability': 'teaching', 'scope': 'self', 'scope_id': ''}]
                   if role == 'teacher' else [
                       {'capability': cap, 'scope': 'all', 'scope_id': ''}
                       for cap in ['admin', 'review', 'publish']])
    if role == 'teacher':
        from app.services.teacher_positions import position_grants
        user.grants.extend(position_grants(teacher))
    return user
