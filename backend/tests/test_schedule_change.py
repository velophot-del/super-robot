import unittest
from datetime import date, datetime
import test_debug_mode
from app.models.planning import (AcademicPlan, PublishedPlan, TeachingAssignment, TeachingTask,
    MatchRun, TeacherNotification, TeacherScheduleConfirmation, ScheduleChangeRequest,
    ScheduleChangeDecision)


class ScheduleChangeTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown = test_debug_mode.DebugModeTests.asyncTearDown

    async def _headers(self, role, teacher_id=None):
        result = await self.client.post('/api/debug/session', json={'role': role, 'teacher_id': teacher_id})
        self.assertEqual(result.status_code, 200, result.text)
        return {'Authorization': 'Bearer ' + result.json()['access_token']}

    async def _published(self):
        plan = AcademicPlan(id=1, name='春季排课', start_date=date(2027, 3, 1), weeks=20,
            deadline=datetime(2027, 2, 1), state='published', settings={})
        self.db.add(plan); self.db.flush()
        self.db.add(MatchRun(id=1, plan_id=1, payload={}))
        task = TeachingTask(id=1, plan_id=1, payload={'name':'设计基础','code':'D1','group':'视传2601',
            'class_name':'视传2601','department':'视觉传达设计','teacher_count':1,'required_hours':2,
            'start_week':1,'end_week':1,'tail_weeks':0,'room_id':None,'slots':[]})
        self.db.add(task); self.db.flush()
        self.db.add(TeachingAssignment(task_id=1, teacher_ids=[7], match_id=1, locked=True))
        payload={'plan':{'id':1,'name':'春季排课','start_date':'2027-03-01','weeks':20},
            'tasks':[{'id':1,'plan_id':1,'name':'设计基础','code':'D1','group':'视传2601',
                'class_name':'视传2601','department':'视觉传达设计','teacher_count':1,'teacher_ids':[7],
                'teacher_names':['Demo teacher'],'locked':True,'required_hours':2,'start_week':1,
                'end_week':1,'tail_weeks':0,'room_id':None,'room_name':None,
                'slots':[{'day':1,'start':1,'count':1,'phase':'normal'}]}]}
        snapshot=PublishedPlan(id=1,plan_id=1,payload=payload)
        self.db.add(snapshot);self.db.commit()
        return payload

    async def test_only_assigned_teacher_can_confirm_and_submit_change(self):
        await self._published()
        headers=await self._headers('teacher',7)
        denied=await self.client.post('/api/planning/plans/1/confirm-schedule',headers=headers,
            json={'snapshot_id':1,'task_id':999})
        self.assertEqual(denied.status_code,403)
        confirmed=await self.client.post('/api/planning/plans/1/confirm-schedule',headers=headers,
            json={'snapshot_id':1,'task_id':1,'note':'已核对'})
        self.assertEqual(confirmed.status_code,200,confirmed.text)
        duplicate=await self.client.post('/api/planning/plans/1/confirm-schedule',headers=headers,
            json={'snapshot_id':1,'task_id':1})
        self.assertEqual(duplicate.status_code,409)
        request=await self.client.post('/api/planning/plans/1/change-requests',headers=headers,
            json={'snapshot_id':1,'task_id':1,'reason':'本人周一有固定教学安排','desired_change':'希望调整到周三'})
        self.assertEqual(request.status_code,200,request.text)
        other=await self._headers('teacher',7)
        self.assertEqual((await self.client.post('/api/planning/plans/1/confirm-schedule',headers=other,
            json={'snapshot_id':1,'task_id':1})).status_code,409)
        self.assertEqual(self.db.query(TeacherScheduleConfirmation).count(),1)
        self.assertEqual(self.db.query(ScheduleChangeRequest).count(),1)

    async def test_approval_creates_revision_and_preserves_published_snapshot(self):
        payload=await self._published()
        teacher=await self._headers('teacher',7)
        request=(await self.client.post('/api/planning/plans/1/change-requests',headers=teacher,
            json={'snapshot_id':1,'task_id':1,'reason':'本人周一有固定教学安排'})).json()
        admin=await self._headers('admin')
        response=await self.client.post(f"/api/planning/plans/1/change-requests/{request['request_id']}/decision",
            headers=admin,json={'approve':True,'reason':'批准调整'})
        self.assertEqual(response.status_code,200,response.text)
        revision_id=response.json()['revision_plan_id']
        revision=self.db.get(AcademicPlan,revision_id)
        self.assertEqual(revision.state,'draft')
        self.assertEqual(revision.settings['supersedes_plan_id'],1)
        self.assertEqual(self.db.get(PublishedPlan,1).payload,payload)
        self.assertEqual(self.db.query(ScheduleChangeDecision).one().decision,'approved')
        self.assertEqual(self.db.query(TeacherNotification).count(),1)
        listed=(await self.client.get('/api/planning/plans/1/change-requests',headers=admin)).json()
        self.assertEqual(listed[0]['status'],'approved')


if __name__ == '__main__':
    unittest.main()
