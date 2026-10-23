import unittest
from datetime import date,datetime
import test_debug_mode
from app.models.classroom import Classroom
from app.models.planning import AcademicPlan,MatchRun,TeachingAssignment,TeachingTask
from app.models.planning import PeriodSlot


class AutoScheduleTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown=test_debug_mode.DebugModeTests.asyncTearDown

    async def test_auto_schedule_places_locked_task_and_preserves_exact_hours(self):
        self.db.add(Classroom(id=1,name='R101',room_code='R101',capacity=40,room_type='普通教室',is_available=True))
        plan=AcademicPlan(id=1,name='Auto',start_date=date(2026,2,2),weeks=20,
            deadline=datetime(2026,1,1),state='matched',settings={'groups':['G']})
        self.db.add(plan);self.db.flush()
        self.db.add(MatchRun(id=1,plan_id=1,payload={'plan_revision':1}))
        task=TeachingTask(id=1,plan_id=1,payload={'name':'Design','code':'D1','group':'G','class_name':'G',
            'cohort':'2026','required_hours':4,'start_week':1,'end_week':2,'tail_weeks':0,
            'teacher_count':1,'max_students':30,'room_id':None,'room_type':'','slots':[],
            'source':{'course_metadata':{'weekly_hours':2,'teaching_weeks':2,'hours_per_session':2}}})
        self.db.add(task);self.db.flush()
        self.db.add(TeachingAssignment(task_id=1,teacher_ids=[7],match_id=1,locked=True));self.db.commit()
        headers={'Authorization':'Bearer '+(await self.client.post('/api/debug/session',json={'role':'admin'})).json()['access_token']}
        response=await self.client.post('/api/planning/plans/1/auto-schedule',headers=headers)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['scheduled'],1)
        placed=self.db.get(TeachingTask,1)
        slots=self.db.query(PeriodSlot).filter_by(task_id=1).all()
        self.assertEqual(placed.payload['room_id'],1)
        self.assertEqual(sum(s.count for s in slots)*2,4)

    async def test_auto_schedule_does_not_partially_write_when_no_room_exists(self):
        plan=AcademicPlan(id=1,name='Auto',start_date=date(2026,2,2),weeks=20,
            deadline=datetime(2026,1,1),state='matched',settings={'groups':['G']})
        self.db.add(plan);self.db.flush();self.db.add(MatchRun(id=1,plan_id=1,payload={'plan_revision':1}))
        self.db.add(TeachingTask(id=1,plan_id=1,payload={'name':'Design','code':'D1','group':'G','class_name':'G',
            'required_hours':2,'start_week':1,'end_week':1,'tail_weeks':0,'teacher_count':1,
            'room_id':None,'slots':[],'source':{'course_metadata':{'weekly_hours':2,'teaching_weeks':1}}}))
        self.db.flush();self.db.add(TeachingAssignment(task_id=1,teacher_ids=[7],match_id=1,locked=True));self.db.commit()
        headers={'Authorization':'Bearer '+(await self.client.post('/api/debug/session',json={'role':'admin'})).json()['access_token']}
        response=await self.client.post('/api/planning/plans/1/auto-schedule',headers=headers)
        self.assertEqual(response.status_code,409)
        self.assertEqual(self.db.query(PeriodSlot).count(),0)

    async def test_genetic_preview_is_read_only_until_admin_applies_candidate(self):
        self.db.add(Classroom(id=1,name='R101',room_code='R101',capacity=40,room_type='普通教室',is_available=True))
        plan=AcademicPlan(id=1,name='GA preview',start_date=date(2026,2,2),weeks=20,
            deadline=datetime(2026,1,1),state='matched',settings={'groups':['G']})
        self.db.add(plan);self.db.flush();self.db.add(MatchRun(id=1,plan_id=1,payload={'plan_revision':1}))
        task=TeachingTask(id=1,plan_id=1,payload={'name':'Design','code':'D1','group':'G','class_name':'G',
            'cohort':'2026','required_hours':4,'start_week':1,'end_week':2,'tail_weeks':0,
            'teacher_count':1,'max_students':30,'room_id':None,'room_type':'','slots':[],
            'source':{'course_metadata':{'weekly_hours':2,'teaching_weeks':2,'hours_per_session':2}}})
        self.db.add(task);self.db.flush()
        self.db.add(TeachingAssignment(task_id=1,teacher_ids=[7],match_id=1,locked=True));self.db.commit()
        headers={'Authorization':'Bearer '+(await self.client.post('/api/debug/session',json={'role':'admin'})).json()['access_token']}
        preview=await self.client.post('/api/planning/plans/1/auto-schedule/preview',headers=headers,
            json={'algorithm':'genetic'})
        self.assertEqual(preview.status_code,200,preview.text)
        candidate=preview.json()
        self.assertEqual(candidate['algorithm'],'genetic')
        self.assertEqual(candidate['tasks'][0]['teacher_ids'],[7])
        self.assertEqual(candidate['tasks'][0]['start_week'],1)
        self.assertEqual(self.db.query(PeriodSlot).count(),0)
        self.assertIsNone(self.db.get(TeachingTask,1).payload['room_id'])

        applied=await self.client.post('/api/planning/plans/1/auto-schedule/apply',headers=headers,
            json={'preview_id':candidate['preview_id']})
        self.assertEqual(applied.status_code,200,applied.text)
        self.assertGreater(self.db.query(PeriodSlot).count(),0)
        self.assertEqual(self.db.get(TeachingAssignment,1).teacher_ids,[7])
        repeated=await self.client.post('/api/planning/plans/1/auto-schedule/apply',headers=headers,
            json={'preview_id':candidate['preview_id']})
        self.assertEqual(repeated.status_code,409)


if __name__=='__main__':
    unittest.main()
