import unittest
import test_debug_mode
import test_planning_workflow
from app.models.teacher import Teacher
from app.models.planning import PreferenceSubmission


class WorkloadEstimatesTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown=test_debug_mode.DebugModeTests.asyncTearDown
    headers=test_planning_workflow.PlanningWorkflowTests.headers
    plan=test_planning_workflow.PlanningWorkflowTests.plan
    task=test_planning_workflow.PlanningWorkflowTests.task

    async def prepare(self):
        pid=await self.plan();admin=await self.headers();teacher=await self.headers('teacher')
        task=(await self.client.post(f'/api/planning/plans/{pid}/tasks',headers=admin,json=self.task())).json()
        self.assertEqual((await self.client.post(f'/api/planning/plans/{pid}/open',headers=admin)).status_code,200)
        state=(await self.client.get(f'/api/planning/plans/{pid}',headers=teacher)).json()
        await self.client.put(f'/api/planning/plans/{pid}/draft',headers=teacher,json={'revision':0,'plan_revision':state['revision'],'task_ids':[task['id']]})
        return pid,task['id'],teacher,admin

    async def test_save_reload_stale_and_teacher_isolation(self):
        pid,tid,h,admin=await self.prepare()
        url=f'/api/planning/plans/{pid}/tasks/{tid}/workload-estimate'
        saved=await self.client.put(url,headers=h,json={'revision':0,'weekly_hours':4,'weeks':5,'guidance_students':3})
        self.assertEqual(saved.status_code,200,saved.text)
        self.assertEqual(saved.json()['revision'],1)
        state=(await self.client.get(f'/api/planning/plans/{pid}',headers=h)).json()
        self.assertEqual(state['workload_estimates'][str(tid)]['weekly_hours'],4)
        self.assertEqual((await self.client.put(url,headers=h,json={'revision':0,'weeks':2})).status_code,409)
        self.assertEqual((await self.client.put(url,headers=admin,json={'revision':1,'weeks':2})).status_code,403)
        self.db.add(Teacher(id=8,name='Other',teacher_code='OTHER'));self.db.commit()
        token=(await self.client.post('/api/debug/session',json={'role':'teacher','teacher_id':8})).json()['access_token']
        other=await self.client.get(f'/api/planning/plans/{pid}',headers={'Authorization':'Bearer '+token})
        self.assertEqual(other.json()['workload_estimates'],{})
        forged=await self.client.put(url,headers=h,json={'revision':1,'teacher_id':8,'weeks':2})
        self.assertEqual(forged.status_code,422)

    async def test_estimates_do_not_modify_submissions_and_invalid_inputs_are_rejected(self):
        pid,tid,h,_=await self.prepare();url=f'/api/planning/plans/{pid}/tasks/{tid}/workload-estimate'
        self.assertEqual((await self.client.post(f'/api/planning/plans/{pid}/submit',headers=h,json={'revision':1})).status_code,200)
        original=[(s.id,s.task_ids,s.draft_revision) for s in self.db.query(PreferenceSubmission)]
        for values in [{'weekly_hours':-1},{'weeks':21},{'guidance_students':-1},{'guidance_kind':'unknown'}]:
            self.assertEqual((await self.client.put(url,headers=h,json={'revision':0,**values})).status_code,422)
        result=await self.client.put(url,headers=h,json={'revision':0,'guidance_students':0})
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual([(s.id,s.task_ids,s.draft_revision) for s in self.db.query(PreferenceSubmission)],original)
        self.assertEqual((await self.client.put(f'/api/planning/plans/{pid}/tasks/999/workload-estimate',headers=h,json={'revision':0,'weeks':2})).status_code,404)
