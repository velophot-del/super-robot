import unittest
import test_debug_mode
from app.models.class_info import ClassInfo
from app.models.course import Course


class CourseCatalogWorkflowTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown = test_debug_mode.DebugModeTests.asyncTearDown

    async def admin_headers(self):
        token = (await self.client.post('/api/debug/session', json={'role': 'admin'})).json()['access_token']
        return {'Authorization': f'Bearer {token}'}

    async def test_bulk_update_and_remove_keep_course_record_as_inactive(self):
        self.db.add_all([
            Course(name='Design A', course_code='A1', semester=1, department='Design'),
            Course(name='Design B', course_code='B1', semester=1, department='Design'),
        ])
        self.db.commit()
        headers = await self.admin_headers()

        updated = await self.client.patch('/api/courses/bulk', headers=headers, json={
            'ids': [1, 2], 'updates': {'course_type': '综合实践课', 'course_nature': '限选课'}
        })
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()['updated'], 2)
        self.assertEqual({row.course_type for row in self.db.query(Course)}, {'综合实践课'})

        removed = await self.client.request('DELETE', '/api/courses/bulk', headers=headers, json={'ids': [1, 2]})
        self.assertEqual(removed.status_code, 200, removed.text)
        self.assertEqual(removed.json()['removed'], 2)
        self.assertEqual(self.db.query(Course).filter(Course.is_active.is_(True)).count(), 0)
        self.assertEqual(self.db.query(Course).count(), 2)

        restored = await self.client.put('/api/courses/1', headers=headers, json={'is_active': True})
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(self.db.query(Course).filter(Course.is_active.is_(True)).count(), 1)

    async def test_cycle_uses_course_catalog_and_excludes_graduated_cohorts(self):
        headers = await self.admin_headers()
        self.db.add_all([
            ClassInfo(name='视觉2601', grade='2026', department='视觉传达设计', student_count=30),
            ClassInfo(name='视觉2101', grade='2021', department='视觉传达设计', student_count=30),
        ])
        self.db.add_all([
            Course(name='构成设计', course_code='VC-2602', semester=2, cohort='2026',
                   department='视觉传达设计', total_hours=48, teaching_weeks=6),
            Course(name='旧年级课程', course_code='VC-2102', semester=2, cohort='2021',
                   department='视觉传达设计', total_hours=48, teaching_weeks=6),
        ])
        self.db.commit()

        created = await self.client.post('/api/planning/plans', headers=headers, json={
            'name': '课程库排课周期', 'start_date': '2027-03-08', 'weeks': 20,
            'deadline': '2027-02-28T23:59:59', 'global_cycle': True, 'term': 2,
            'rule_confirmed': True,
        })
        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(created.json()['groups'], ['视觉2601'])

        generated = await self.client.post(
            f"/api/planning/plans/{created.json()['id']}/generate", headers=headers)
        self.assertEqual(generated.status_code, 200, generated.text)
        self.assertEqual(generated.json()['added'], 1)

        state = (await self.client.get(
            f"/api/planning/plans/{created.json()['id']}", headers=headers)).json()
        self.assertEqual([(task['name'], task['group'], task['cohort']) for task in state['tasks']],
                         [('构成设计', '视觉2601', '2026')])
        pool = (await self.client.get(
            f"/api/planning/plans/{created.json()['id']}/course-pool", headers=headers)).json()
        self.assertEqual([course['code'] for course in pool['courses']], ['VC-2602'])


if __name__ == '__main__':
    unittest.main()
