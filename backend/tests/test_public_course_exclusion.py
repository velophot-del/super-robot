"""公共课（学科通识课/德育通识课）默认从课程库列表和排课池排除，数据仍保留。"""
import unittest
import test_debug_mode
from app.models.class_info import ClassInfo
from app.models.course import Course


class PublicCourseExclusionTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown = test_debug_mode.DebugModeTests.asyncTearDown

    async def admin_headers(self):
        token = (await self.client.post('/api/debug/session', json={'role': 'admin'})).json()['access_token']
        return {'Authorization': f'Bearer {token}'}

    async def test_course_list_hides_public_courses_unless_requested(self):
        self.db.add_all([
            Course(name='专业课', course_code='D1', course_type='专业课'),
            Course(name='公共英语', course_code='P1', course_type='学科通识课'),
            Course(name='思政', course_code='P2', course_type='德育通识课'),
            Course(name='历史公共课', course_code='LEGACY', course_type='公共课'),
        ])
        self.db.commit()
        headers = await self.admin_headers()

        visible = (await self.client.get('/api/courses/', headers=headers)).json()
        self.assertEqual({row['course_code'] for row in visible}, {'D1'})

        all_rows = (await self.client.get(
            '/api/courses/', params={'include_public': 'true'}, headers=headers)).json()
        self.assertEqual({row['course_code'] for row in all_rows}, {'D1', 'P1', 'P2', 'LEGACY'})
        self.assertEqual(self.db.query(Course).count(), 4)

    async def test_cycle_generation_and_course_pool_exclude_public_courses(self):
        self.db.add(ClassInfo(name='视觉2601', grade='2026', department='视觉传达设计', student_count=30))
        self.db.add_all([
            Course(name='构成设计', course_code='VC-2602', semester=2, cohort='2026',
                   department='视觉传达设计', total_hours=48, teaching_weeks=6),
            Course(name='公共英语', course_code='PB-2602', semester=2, cohort='2026',
                   department='视觉传达设计', course_type='学科通识课',
                   total_hours=48, teaching_weeks=6),
            Course(name='思政', course_code='SZ-2602', semester=2, cohort='2026',
                   department='视觉传达设计', course_type='德育通识课',
                   total_hours=48, teaching_weeks=6),
        ])
        self.db.commit()
        headers = await self.admin_headers()

        created = await self.client.post('/api/planning/plans', headers=headers, json={
            'name': '公共课排除', 'start_date': '2027-03-08', 'weeks': 20,
            'deadline': '2027-02-28T23:59:59', 'global_cycle': True, 'term': 2,
            'rule_confirmed': True,
        })
        self.assertEqual(created.status_code, 200, created.text)
        plan_id = created.json()['id']

        generated = await self.client.post(f'/api/planning/plans/{plan_id}/generate', headers=headers)
        self.assertEqual(generated.status_code, 200, generated.text)
        self.assertEqual(generated.json()['added'], 1)

        pool = (await self.client.get(
            f'/api/planning/plans/{plan_id}/course-pool', headers=headers)).json()
        self.assertEqual([course['code'] for course in pool['courses']], ['VC-2602'])

        state = (await self.client.get(
            f'/api/planning/plans/{plan_id}', headers=headers)).json()
        self.assertEqual([task['name'] for task in state['tasks']], ['构成设计'])
