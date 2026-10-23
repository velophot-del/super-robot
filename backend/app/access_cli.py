"""真实账号的显式授权入口；默认只预览，绝不按旧角色自动提权。"""
import argparse
from app.database import init_db, SessionLocal
from app.models.user import User
from app.models.teacher import Teacher
from app.models.planning import AccountGrant, TeacherBinding


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--user-id',type=int,required=True)
    parser.add_argument('--capability',choices=['admin','teaching','lead','review','publish'],required=True)
    parser.add_argument('--scope',choices=['all','self','dept','course'],default='self')
    parser.add_argument('--scope-id',default='')
    parser.add_argument('--teacher-id',type=int)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args();init_db()
    with SessionLocal() as db:
        user=db.get(User,args.user_id)
        if not user:raise SystemExit('指定账号不存在')
        if args.scope in {'dept','course'} and not args.scope_id:raise SystemExit('必须明确课程代码或课程所属教研室')
        if args.capability=='lead' and args.scope!='dept':raise SystemExit('教研室主任职能必须限定到dept范围')
        binding=db.get(TeacherBinding,user.id)
        if args.teacher_id and not db.get(Teacher,args.teacher_id):raise SystemExit('教师不存在')
        if args.capability=='teaching' and not args.teacher_id and not binding:raise SystemExit('教学职能需要绑定教师')
        if args.capability=='lead' and not args.teacher_id and not binding:raise SystemExit('教研室主任必须绑定教师，并同时具有本人教学职能')
        bundle='，并授予本人教学职能' if args.capability=='lead' else ''
        print(f'账号{user.id} {user.username}: {args.capability}@{args.scope} {args.scope_id}{bundle}，绑定教师{args.teacher_id or (binding.teacher_id if binding else "无")}')
        if not args.apply:print('预览完成；未修改。明确确认后添加 --apply 才生效。');return
        if args.teacher_id:
            if binding and binding.teacher_id!=args.teacher_id:raise SystemExit('已有不同教师绑定，不能静默覆盖')
            occupied=db.query(TeacherBinding).filter_by(teacher_id=args.teacher_id).first()
            if occupied and occupied.user_id!=user.id:raise SystemExit('该教师已绑定其他账号')
            if not binding:db.add(TeacherBinding(user_id=user.id,teacher_id=args.teacher_id))
        exists=db.query(AccountGrant).filter_by(user_id=user.id,capability=args.capability,scope=args.scope,scope_id=args.scope_id).first()
        if not exists:db.add(AccountGrant(user_id=user.id,capability=args.capability,scope=args.scope,scope_id=args.scope_id))
        if args.capability=='lead':
            teaching=db.query(AccountGrant).filter_by(user_id=user.id,capability='teaching',scope='self',scope_id='').first()
            if not teaching:db.add(AccountGrant(user_id=user.id,capability='teaching',scope='self',scope_id=''))
        db.commit();print('已写入明确授权')


if __name__=='__main__':main()
