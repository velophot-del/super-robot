from datetime import date, datetime
import unittest
import test_debug_mode
from app.models.planning import AcademicPlan, PublishedPlan


class TeacherWorkbenchTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown = test_debug_mode.DebugModeTests.asyncTearDown

    async def headers(self, role='teacher'):
        payload = {'role': role}
        if role == 'teacher':
            payload['teacher_id'] = 7
        response = await self.client.post('/api/debug/session', json=payload)
        return {'Authorization': 'Bearer ' + response.json()['access_token']}

    async def test_timetable_uses_latest_immutable_snapshot_and_only_own_tasks(self):
        plan = AcademicPlan(name='Historical plan', start_date=date(2025, 9, 1), weeks=20,
                            deadline=datetime(2025, 8, 1), state='published', settings={})
        self.db.add(plan)
        self.db.flush()
        info = {'id': plan.id, 'name': plan.name, 'start_date': '2025-09-01', 'weeks': 20,
                'academic_year': '2025—2026', 'academic_term': 1}
        self.db.add(PublishedPlan(plan_id=plan.id, payload={'plan': info, 'tasks': [
            {'id': 1, 'name': 'Old snapshot', 'teacher_ids': [7]}]}))
        self.db.flush()
        self.db.add(PublishedPlan(plan_id=plan.id, payload={'plan': info, 'tasks': [
            {'id': 2, 'name': 'My course', 'teacher_ids': [7]},
            {'id': 3, 'name': 'Other teacher', 'teacher_ids': [99]}]}))
        plan.name = 'Mutable name must not leak'
        self.db.commit()
        response = await self.client.get('/api/my/planning-timetable?teacher_id=99', headers=await self.headers())
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(len(result['batches']), 1)
        self.assertEqual(result['batches'][0]['plan']['name'], 'Historical plan')
        self.assertEqual([t['id'] for t in result['batches'][0]['tasks']], [2])
        self.assertNotEqual(result['current_period'], {'academic_year': '2025—2026', 'academic_term': 1})
        self.assertEqual(result['legacy_versions'], [])

    async def test_timetable_requires_bound_teacher(self):
        self.assertEqual((await self.client.get('/api/my/planning-timetable')).status_code, 401)
        response = await self.client.get('/api/my/planning-timetable', headers=await self.headers('admin'))
        self.assertEqual(response.status_code, 403)
