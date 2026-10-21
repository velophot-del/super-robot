"""仅管理员名单导入调用；不认领既有账号或重置密码。"""
from uuid import uuid4
from fastapi import HTTPException
from app.models.user import User, AccountSetup
from app.models.planning import TeacherBinding, AccountGrant
from app.services.auth import hash_password


def provision_teacher_account(db, teacher):
    binding = db.query(TeacherBinding).filter_by(teacher_id=teacher.id).first()
    if binding:
        return False
    username = teacher.teacher_code.strip()
    if not username or len(username) > 50:
        raise HTTPException(422, '教师工号必须为1—50个字符')
    if db.query(User).filter_by(username=username).first():
        raise HTTPException(409, f'工号{username}与已有账号冲突，未覆盖或绑定；请管理员核对')
    user = User(username=username, email=f'{uuid4().hex}@accounts.invalid',
                password_hash=hash_password('123456'))
    db.add(user); db.flush()
    db.add_all([TeacherBinding(user_id=user.id, teacher_id=teacher.id),
                AccountGrant(user_id=user.id, capability='teaching', scope='self', scope_id=''),
                AccountSetup(user_id=user.id, password_changed=False, token_version=0)])
    db.flush()
    return True
