import unittest
from types import SimpleNamespace
from app.services.authorization import can
from app.services.teacher_course_matching import score_candidate
from app.models.planning import AcademicPlan
from datetime import date
import test_debug_mode


class PlanningConstraintTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown=test_debug_mode.DebugModeTests.asyncTearDown

    async def test_permissions_depend_on_scope_not_role(self):
        user=SimpleNamespace(role='admin',teacher_id=7,grants=[])
        self.assertFalse(can(user,'admin'))
        user.grants=[{'capability':'review','scope':'dept','scope_id':'Design'}]
        self.assertTrue(can(user,'review',{'department':'Design'}))
        self.assertFalse(can(user,'review',{'department':'Other'}))
        self.assertFalse(can(user,'publish'))

    async def test_unknown_profile_and_capacity_are_not_hidden_by_score(self):
        plan=AcademicPlan(id=1,start_date=date(2027,2,1),weeks=20)
        task={'id':1,'name':'Typography','code':'A','group':'G','required_hours':4,
            'start_week':1,'end_week':1,'direction':'Design','tags':['type'],
            'profile_verified':True,'slots':[{'day':1,'start':1,'count':4}]}
        result=score_candidate(self.db,plan,task,7,{},0,[])
        self.assertIsNone(result['professional_fit']);self.assertIsNone(result['raw_total'])
        profile={'direction':'Design','tags':['type'],'verified':True,'team_codes':['A'],
            'taught_codes':['A'],'external_hours':{'1':20},'weekly_limit':20}
        result=score_candidate(self.db,plan,task,7,profile,0,[])
        self.assertEqual(result['professional_fit'],100)
        self.assertFalse(result['eligible'])
        self.assertIn('外部',result['reasons'][0])

    async def test_published_plan_also_reserves_student_group(self):
        from app.models.planning import TeachingTask,PeriodSlot
        from app.services.stage_planning import validate_tasks
        from fastapi import HTTPException
        from datetime import datetime
        prior=AcademicPlan(id=3,name='Published',start_date=date(2027,2,1),weeks=20,
            deadline=datetime(2027,1,1),state='published')
        self.db.add(prior);self.db.flush()
        payload={'name':'Other','code':'B','group':'G','required_hours':4,'start_week':1,'end_week':1}
        self.db.add(TeachingTask(id=8,plan_id=3,payload=payload));self.db.flush()
        self.db.add(PeriodSlot(task_id=8,day=1,start=5,count=4));self.db.commit()
        current=AcademicPlan(id=4,start_date=date(2027,2,1),weeks=20)
        task={**payload,'code':'A','slots':[{'day':1,'start':1,'count':4}]}
        with self.assertRaises(HTTPException) as raised:validate_tasks(self.db,current,[task])
        self.assertIn('教学组',raised.exception.detail)

    async def test_immutable_audit_records_reject_raw_database_changes(self):
        from app.models.planning import PlanningEvent
        from app.services.immutable_records import install_immutable_triggers
        from sqlalchemy import text
        from sqlalchemy.exc import IntegrityError
        self.db.add(PlanningEvent(actor='test',action='test',payload={}));self.db.commit()
        install_immutable_triggers(self.engine)
        with self.assertRaises(IntegrityError):
            self.db.execute(text("UPDATE planning_events SET action='tampered'"));self.db.commit()
        self.db.rollback()

    async def test_split_student_groups_do_not_merge_unrelated_courses(self):
        from app.models.planning import TeachingTask,PeriodSlot
        from app.services.stage_planning import validate_tasks
        from datetime import datetime
        prior=AcademicPlan(id=5,name='Published',start_date=date(2027,2,1),weeks=20,deadline=datetime(2027,1,1),state='published')
        self.db.add(prior);self.db.flush()
        for tid,code,group,student,day in [(10,'B','G1','s1',2),(11,'C','G2','s2',3)]:
            self.db.add(TeachingTask(id=tid,plan_id=5,payload={'name':code,'code':code,'group':group,'student_ids':[student],'required_hours':4,'start_week':1,'end_week':1}));self.db.flush()
            self.db.add(PeriodSlot(task_id=tid,day=day,start=1,count=4))
        self.db.commit()
        task={'name':'A','code':'A','group':'G','student_ids':['s1','s2'],'required_hours':4,'start_week':1,'end_week':1,'slots':[{'day':1,'start':1,'count':4}]}
        validate_tasks(self.db,AcademicPlan(id=6,start_date=date(2027,2,1),weeks=20),[task])
