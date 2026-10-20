import unittest
import test_debug_mode


class PlanningWorkflowTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown = test_debug_mode.DebugModeTests.asyncTearDown

    async def headers(self, role='admin'):
        data = {'role': role}
        if role == 'teacher': data['teacher_id'] = 7
        response = await self.client.post('/api/debug/session', json=data)
        headers={'Authorization': 'Bearer ' + response.json()['access_token']}
        if role=='teacher':
            profile=(await self.client.get('/api/planning/self-profile',headers=headers)).json()
            if not profile['ready']:
                saved=await self.client.put('/api/planning/self-profile',headers=headers,json={'revision':profile['revision'],'direction':'Design','tags':['type'],'skilled_courses':['Typography']})
                self.assertEqual(saved.status_code,200,saved.text)
        return headers

    async def plan(self):
        h = await self.headers()
        from app.models.classroom import Classroom
        if not self.db.get(Classroom,31):
            self.db.add(Classroom(id=31,name='Room',room_code='R31',capacity=40));self.db.commit()
        r = await self.client.post('/api/planning/plans', headers=h, json={
            'name': 'Test term', 'start_date': '2027-02-01', 'weeks': 20,
            'deadline': '2027-01-31T23:59:59', 'rule_confirmed': True})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()['id']

    def task(self, code='A', day=1):
        return {'name': 'Typography', 'code': code, 'group': 'Class A', 'department': 'Design',
            'credits': 1.5, 'required_hours': 8, 'start_week': 1, 'end_week': 2,
            'direction': 'Design', 'tags': ['type'], 'profile_verified': True,
            'slots': [{'day': day, 'start': 1, 'count': 4}], 'teacher_count': 1, 'room_id':31}

    async def test_two_courses_allowed_third_rejected_and_teacher_no_write(self):
        pid = await self.plan(); admin = await self.headers(); teacher = await self.headers('teacher')
        for code, day in [('A', 1), ('B', 2)]:
            r = await self.client.post(f'/api/planning/plans/{pid}/tasks', headers=admin, json=self.task(code, day))
            self.assertEqual(r.status_code, 200, r.text)
        r = await self.client.post(f'/api/planning/plans/{pid}/tasks', headers=admin, json=self.task('C', 3))
        self.assertEqual(r.status_code, 409)
        self.assertIn('2门', r.text)
        r = await self.client.post(f'/api/planning/plans/{pid}/tasks', headers=teacher, json=self.task('D', 4))
        self.assertEqual(r.status_code, 403)

    async def test_draft_submission_matching_review_and_stale_save(self):
        pid = await self.plan(); admin = await self.headers(); teacher = await self.headers('teacher')
        r = await self.client.post(f'/api/planning/plans/{pid}/tasks', headers=admin, json=self.task())
        self.assertEqual(r.status_code, 200, r.text); task_id = r.json()['id']
        r = await self.client.put('/api/planning/profiles/7', headers=admin, json={
            'direction': 'Design', 'tags': ['type'], 'verified': True,
            'team_codes': ['A'], 'taught_codes': ['A'], 'weekly_limit': 20, 'course_limit': 3})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((await self.client.post(f'/api/planning/plans/{pid}/open', headers=admin)).status_code, 200)
        state = (await self.client.get(f'/api/planning/plans/{pid}', headers=teacher)).json()
        data = {'revision': 0, 'plan_revision': state['revision'], 'task_ids': [task_id]}
        saved = await self.client.put(f'/api/planning/plans/{pid}/draft', headers=teacher, json=data)
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual((await self.client.put(f'/api/planning/plans/{pid}/draft', headers=teacher, json=data)).status_code, 409)
        submitted = await self.client.post(f'/api/planning/plans/{pid}/submit', headers=teacher,
                                          json={'revision': saved.json()['revision']})
        self.assertEqual(submitted.status_code, 200, submitted.text)
        matched = await self.client.post(f'/api/planning/plans/{pid}/match', headers=admin)
        self.assertEqual(matched.status_code, 200, matched.text)
        candidate = matched.json()['candidates'][0]
        self.assertEqual(candidate['professional_fit'], 100)
        self.assertEqual(len(candidate['components']), 6)
        self.assertEqual(matched.json()['maximum'], 105)
        duplicate = await self.client.post(f'/api/planning/plans/{pid}/assign', headers=admin,
            json={'task_id': task_id, 'teacher_ids': [7,7], 'match_id': matched.json()['id'], 'reason': 'Duplicate'})
        self.assertEqual(duplicate.status_code,422,duplicate.text)
        confirmed = await self.client.post(f'/api/planning/plans/{pid}/assign', headers=admin,
            json={'task_id': task_id, 'teacher_ids': [7], 'match_id': matched.json()['id'], 'reason': 'Reviewed'})
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        state = (await self.client.get(f'/api/planning/plans/{pid}', headers=teacher)).json()
        self.assertEqual(state['tasks'][0]['teacher_ids'], [7])

    async def test_missing_profile_is_unknown_and_same_day_reserved(self):
        pid = await self.plan(); admin = await self.headers()
        r = await self.client.post(f'/api/planning/plans/{pid}/tasks', headers=admin, json=self.task())
        self.assertEqual(r.status_code, 200, r.text)
        another = self.task('B', 1); another['slots'] = [{'day': 1, 'start': 5, 'count': 4}]
        r = await self.client.post(f'/api/planning/plans/{pid}/tasks', headers=admin, json=another)
        self.assertEqual(r.status_code, 409)
        self.assertIn('同日', r.text)

    async def test_publish_requires_room_and_export_uses_snapshot(self):
        from app.models.classroom import Classroom
        self.db.add(Classroom(id=31,name='Room',room_code='R31',capacity=40));self.db.commit()
        pid=await self.plan();admin=await self.headers();teacher=await self.headers('teacher')
        payload=self.task();payload['room_id']=31
        tid=(await self.client.post(f'/api/planning/plans/{pid}/tasks',headers=admin,json=payload)).json()['id']
        await self.client.post(f'/api/planning/plans/{pid}/open',headers=admin)
        s=(await self.client.get(f'/api/planning/plans/{pid}',headers=teacher)).json()
        await self.client.put(f'/api/planning/plans/{pid}/draft',headers=teacher,json={'revision':0,'plan_revision':s['revision'],'task_ids':[tid]})
        await self.client.post(f'/api/planning/plans/{pid}/submit',headers=teacher,json={'revision':1})
        match=(await self.client.post(f'/api/planning/plans/{pid}/match',headers=admin)).json()
        await self.client.post(f'/api/planning/plans/{pid}/assign',headers=admin,json={'task_id':tid,'teacher_ids':[7],'match_id':match['id'],'reason':'manual review of missing profile'})
        r=await self.client.post(f'/api/planning/plans/{pid}/publish',headers=admin)
        self.assertEqual(r.status_code,200,r.text)
        r=await self.client.get(f'/api/planning/plans/{pid}/export',headers=teacher)
        self.assertEqual(r.status_code,200,r.text)
        from openpyxl import load_workbook
        from io import BytesIO
        workbook=load_workbook(BytesIO(r.content))
        self.assertEqual(workbook.active.cell(2,1).value,'Typography')

    async def test_open_requires_room_before_freezing_task(self):
        pid=await self.plan();admin=await self.headers()
        payload=self.task();payload['room_id']=None
        self.assertEqual((await self.client.post(f'/api/planning/plans/{pid}/tasks',headers=admin,json=payload)).status_code,200)
        response=await self.client.post(f'/api/planning/plans/{pid}/open',headers=admin)
        self.assertEqual(response.status_code,409,response.text)
        self.assertIn('地点',response.text)
