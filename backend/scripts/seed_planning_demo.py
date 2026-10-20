"""只向显式独立演示库追加新版示例，不覆盖已有资源或教师档案。"""
import sys
from pathlib import Path
from datetime import date, datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.database import init_db, SessionLocal
from app.models.teacher import Teacher
from app.models.classroom import Classroom
from app.models.planning import AcademicPlan, TeachingTask, PeriodSlot, TeacherProfile


def main():
    if not settings.DEBUG_DEMO_MODE or not settings.DEBUG_DEMO_DATABASE_URL or settings.DATABASE_URL!=settings.DEBUG_DEMO_DATABASE_URL:
        raise SystemExit('需要显式匹配的独立演示数据库配置')
    init_db()
    with SessionLocal() as db:
        name='[新版演示] 2026级视觉传达 · 教师先选课'
        existing=db.query(AcademicPlan).filter_by(name=name).first()
        if existing: print(f'已有演示计划 {existing.id}，保留其状态和所有操作');return
        teachers=db.query(Teacher).order_by(Teacher.id).limit(2).all()
        if len(teachers)<2:raise SystemExit('请先录入至少两位演示教师')
        room=db.query(Classroom).filter(Classroom.is_available==True,Classroom.capacity>=30).first()
        if not room:raise SystemExit('请先录入可用地点')
        for i,t in enumerate(teachers):
            if not db.get(TeacherProfile,t.id):
                code='VCD201' if i==0 else 'VCD202';tag='版式' if i==0 else '品牌'
                db.add(TeacherProfile(teacher_id=t.id,revision=1,payload={'direction':'视觉传达设计','tags':[tag],
                    'verified':True,'team_codes':[code],'taught_codes':[code], 'weekly_limit':20,'course_limit':3,'external_hours':{}}))
        plan=AcademicPlan(name=name,start_date=date(2027,2,1),weeks=20,deadline=datetime(2027,1,31,15,59),
            state='open',revision=1,rule_confirmed=True,settings={'major':'视觉传达设计','cohort':'2026','semester':2,
            'groups':[f'演示视传260{i}' for i in range(1,5)]})
        db.add(plan);db.flush()
        for group_no in range(4):
            for index,(code,title,tag) in enumerate([('VCD201','文字与版式设计','版式'),('VCD202','品牌视觉设计','品牌')]):
                payload={'code':code,'name':title,'group':f'演示视传260{group_no+1}','class_name':f'演示视传260{group_no+1}',
                    'department':'视觉传达设计','credits':2,'required_hours':16,'start_week':1,'end_week':4,'tail_weeks':0,
                    'direction':'视觉传达设计','tags':[tag],'profile_verified':True,'teacher_count':1,'mode':'single',
                    'student_count':30,'student_ids':[],'room_id':room.id,'room_type':'','source':{'kind':'虚构演示，不是正式培养方案'}}
                task=TeachingTask(plan_id=plan.id,payload=payload);db.add(task);db.flush()
                db.add(PeriodSlot(task_id=task.id,day=1+group_no//2+index*2,start=1+(group_no%2)*4,count=4,phase='normal'))
        db.commit();print(f'已追加演示计划 {plan.id}：4教学组×2门，W1—W4，每组同周2门、同日1门；原数据保留')


if __name__=='__main__':main()
