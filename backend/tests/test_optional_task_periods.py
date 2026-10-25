import unittest
import test_debug_mode
import test_planning_workflow


class OptionalTaskPeriodsTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown=test_debug_mode.DebugModeTests.asyncTearDown
    headers=test_planning_workflow.PlanningWorkflowTests.headers
    plan=test_planning_workflow.PlanningWorkflowTests.plan
    task=test_planning_workflow.PlanningWorkflowTests.task

    async def test_periods_can_remain_empty_until_publish_but_must_be_completed_before(self):
        pid=await self.plan();admin=await self.headers();teacher=await self.headers('teacher')
        payload=self.task();payload.pop('slots');payload.pop('room_id')
        payload['tail_weeks']=1;payload['max_students']=30
        created=await self.client.post(f'/api/planning/plans/{pid}/tasks',headers=admin,json=payload)
        self.assertEqual(created.status_code,200,created.text)
        tid=created.json()['id'];self.assertEqual(created.json()['slots'],[])
        self.assertIsNone(created.json()['room_id'])
        opened=await self.client.post(f'/api/planning/plans/{pid}/open',headers=admin)
        self.assertEqual(opened.status_code,200,opened.text)
        state=(await self.client.get(f'/api/planning/plans/{pid}',headers=teacher)).json()
        draft=await self.client.put(f'/api/planning/plans/{pid}/draft',headers=teacher,json={'revision':0,'plan_revision':state['revision'],'task_ids':[tid]})
        self.assertEqual(draft.status_code,200,draft.text)
        submitted=await self.client.post(f'/api/planning/plans/{pid}/submit',headers=teacher,json={'revision':draft.json()['revision']})
        self.assertEqual(submitted.status_code,200,submitted.text)
        matched=await self.client.post(f'/api/planning/plans/{pid}/match',headers=admin)
        self.assertEqual(matched.status_code,200,matched.text)
        self.assertEqual(matched.json()['auto_assigned'],1)
        room=await self.client.put(f'/api/planning/plans/{pid}/tasks/{tid}/room',headers=admin,json={'room_id':31})
        self.assertEqual(room.status_code,200,room.text)
        blocked=await self.client.post(f'/api/planning/plans/{pid}/publish',headers=admin)
        self.assertEqual(blocked.status_code,409,blocked.text)
        revision=(await self.client.get(f'/api/planning/plans/{pid}',headers=admin)).json()['revision']
        scheduled=await self.client.put(f'/api/planning/plans/{pid}/tasks/{tid}/limits',headers=admin,json={
            'revision':revision,'teacher_count':1,'max_students':30,'room_id':31,
            'slots':[{'day':1,'start':1,'count':4,'phase':'normal'},
                     {'day':1,'start':1,'count':4,'phase':'tail'}]})
        self.assertEqual(scheduled.status_code,200,scheduled.text)
        published=await self.client.post(f'/api/planning/plans/{pid}/publish',headers=admin)
        self.assertEqual(published.status_code,200,published.text)
        state=(await self.client.get(f'/api/planning/plans/{pid}',headers=admin)).json()
        self.assertEqual(state['state'],'published')
        self.assertEqual(len(state['tasks'][0]['slots']),2)

    async def test_edit_omitting_hidden_fields_preserves_existing_mode_and_periods(self):
        pid=await self.plan();h=await self.headers()
        payload={**self.task(),'mode':'collaborative','teacher_count':2}
        created=await self.client.post(f'/api/planning/plans/{pid}/tasks',headers=h,json=payload)
        self.assertEqual(created.status_code,200,created.text)
        original=created.json()
        payload.pop('mode');payload.pop('slots');payload['direction']='Revised'
        edited=await self.client.put(f"/api/planning/plans/{pid}/tasks/{original['id']}",headers=h,json=payload)
        self.assertEqual(edited.status_code,200,edited.text)
        self.assertEqual(edited.json()['mode'],'collaborative')
        self.assertEqual(edited.json()['slots'],original['slots'])
        self.assertEqual(edited.json()['room_id'],original['room_id'])

    async def test_optional_periods_do_not_allow_exam_week_or_third_weekly_course(self):
        pid=await self.plan();h=await self.headers()
        for index in range(3):
            payload={**self.task(str(index)), 'group':'G','slots':[],'room_id':None}
            response=await self.client.post(f'/api/planning/plans/{pid}/tasks',headers=h,json=payload)
            self.assertEqual(response.status_code,200 if index<2 else 409,response.text)
        payload={**self.task('EXAM'),'start_week':19,'end_week':20,'slots':[],'room_id':None}
        self.assertEqual((await self.client.post(f'/api/planning/plans/{pid}/tasks',headers=h,json=payload)).status_code,409)
