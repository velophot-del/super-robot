"""显式创建管理员种子账户；重复执行保留密码，不认领同名普通账号。"""
import getpass
from app.database import SessionLocal, init_db
from app.models.user import User
from app.models.planning import AccountGrant
from app.services.auth import hash_password

CAPABILITIES = ('admin', 'review', 'publish')


def seed_admin(db, password):
    user = db.query(User).filter_by(username='admin').first()
    if user:
        grants = {g.capability for g in db.query(AccountGrant).filter_by(
            user_id=user.id, scope='all', scope_id='')}
        if not user.is_active or not set(CAPABILITIES) <= grants:
            raise ValueError('admin 已存在但不是完整管理员，停止以免认领已有账号')
        return user, False
    if not password:
        raise ValueError('密码不能为空')
    user = User(username='admin', email='admin@accounts.invalid',
                password_hash=hash_password(password), is_active=True)
    db.add(user)
    db.flush()
    for capability in CAPABILITIES:
        db.add(AccountGrant(user_id=user.id, capability=capability, scope='all', scope_id=''))
    db.flush()
    return user, True


def main():
    password = getpass.getpass('管理员种子密码: ')
    init_db()
    with SessionLocal() as db:
        with db.begin():
            user, created = seed_admin(db, password)
        print(f'admin (ID={user.id})：' + ('已创建' if created else '已存在，密码和数据保持不变'))


if __name__ == '__main__':
    main()
