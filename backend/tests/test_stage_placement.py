import unittest
import test_debug_mode
from datetime import date,datetime
from app.models.planning import AcademicPlan,CurriculumDocument,ActiveCurriculum


class StagePlacementTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown=test_debug_mode.DebugModeTests.asyncTearDown

    async def test_drop_persists_span_moves_and_rejects_exam_overflow_or_stale(self):
        h={'Authorization':'Bearer '+(await self.client.post('/api/debug/session',json={'role':'admin'})).json()['access_token']}
        row={'code':'A','name':'Typography','credits':4,'required_hours':72,'semester':1,'category':'专业必修课','direction':'Design','tags':['type'],'teaching_weeks':5,'weekly_hours':16,'tail_hours':8,'notes':'最后一周8课时','schedulable':True}
        self.db.add(CurriculumDocument(id=1,name='scheme',major='Design',cohort='2026',revision=1,original=b'test',sha256='hash',rows=[row]));self.db.flush()
        self.db.add(ActiveCurriculum(major='Design',cohort='2026',document_id=1))
        self.db.add(AcademicPlan(id=1,name='Term',start_date=date(2027,9,6),weeks=20,deadline=datetime(2027,8,1),state='draft',revision=1,settings={'major':'Design','cohort':'2026','semester':1,'groups':['A','B']}));self.db.commit()
        r=await self.client.post('/api/planning/curricula/1/sync-courses',headers=h);self.assertEqual(r.status_code,200,r.text)
        r=await self.client.get('/api/planning/plans/1/course-pool',headers=h);self.assertEqual(r.status_code,200,r.text);course=r.json()['courses'][0]
        data={'revision':1,'course_id':course['id'],'group':'A','start_week':2}
        r=await self.client.put('/api/planning/plans/1/placement',headers=h,json=data);self.assertEqual(r.status_code,200,r.text)
        task=r.json()['task'];self.assertEqual((task['start_week'],task['end_week']),(2,6));self.assertEqual(task['tail_weeks'],1)
        self.assertEqual(task['slots'],[])
        self.assertEqual((await self.client.put('/api/planning/plans/1/placement',headers=h,json=data)).status_code,409)
        move={'revision':2,'task_id':task['id'],'group':'B','start_week':7}
        r=await self.client.put('/api/planning/plans/1/placement',headers=h,json=move);self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['task']['end_week'],11)
        move.update(revision=3,start_week=15)
        r=await self.client.put('/api/planning/plans/1/placement',headers=h,json=move);self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['task']['end_week'],19)
        move.update(revision=4,start_week=16)
        self.assertEqual((await self.client.put('/api/planning/plans/1/placement',headers=h,json=move)).status_code,409)
        self.assertEqual((await self.client.post('/api/planning/plans/1/open',headers=h)).status_code,409)

    async def test_moving_manual_course_preserves_tail_periods(self):
        from app.models.planning import TeachingTask,PeriodSlot
        h={'Authorization':'Bearer '+(await self.client.post('/api/debug/session',json={'role':'admin'})).json()['access_token']}
        self.db.add(AcademicPlan(id=1,name='Term',start_date=date(2027,9,6),weeks=20,deadline=datetime(2027,8,1),state='draft',revision=1,settings={'groups':['G']}));self.db.flush()
        self.db.add(TeachingTask(id=1,plan_id=1,payload={'name':'Manual','code':'M','group':'G','start_week':1,'end_week':3,'tail_weeks':1,'required_hours':10,'credits':1}));self.db.flush()
        self.db.add_all([PeriodSlot(task_id=1,day=1,start=1,count=4,phase='normal'),PeriodSlot(task_id=1,day=1,start=1,count=2,phase='tail')]);self.db.commit()
        r=await self.client.put('/api/planning/plans/1/placement',headers=h,json={'revision':1,'task_id':1,'group':'G','start_week':5})
        self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['task']['tail_weeks'],1)
