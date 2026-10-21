import unittest
import test_debug_mode
from app.models.class_info import ClassInfo
from app.models.planning import CurriculumDocument, ActiveCurriculum


class GlobalPlanCycleTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown = test_debug_mode.DebugModeTests.asyncTearDown

    async def test_global_cycle_generates_all_majors_and_cohorts(self):
        headers = {'Authorization': 'Bearer ' + (
            await self.client.post('/api/debug/session', json={'role': 'admin'})).json()['access_token']}
        for name, grade, department in [('视传2401', '2024', '视觉传达设计'),
                                        ('视传2501', '2025', '视觉传达设计'),
                                        ('插画2501', '2025', '插画设计')]:
            self.db.add(ClassInfo(name=name, grade=grade, department=department, student_count=30))

        def row(code, name, semester):
            return {'code': code, 'name': name, 'credits': 2, 'required_hours': 32, 'semester': semester,
                    'category': '专业必修课', 'direction': '', 'tags': [], 'teaching_weeks': 4,
                    'weekly_hours': 8, 'tail_hours': None, 'notes': '', 'schedulable': True}

        self.db.add_all([
            CurriculumDocument(id=1, name='v24', major='视觉传达设计', cohort='2024', revision=1,
                               original=b'x', sha256='h1', rows=[row('D24', '设计基础', 4)]),
            CurriculumDocument(id=2, name='v25', major='视觉传达设计', cohort='2025', revision=1,
                               original=b'x', sha256='h2', rows=[row('D25', '版式设计', 2)]),
            CurriculumDocument(id=3, name='i25', major='插画设计', cohort='2025', revision=1,
                               original=b'x', sha256='h3', rows=[row('I25', '插画基础', 2)]),
        ])
        self.db.add_all([
            ActiveCurriculum(major='视觉传达设计', cohort='2024', document_id=1),
            ActiveCurriculum(major='视觉传达设计', cohort='2025', document_id=2),
            ActiveCurriculum(major='插画设计', cohort='2025', document_id=3),
        ])
        self.db.commit()

        response = await self.client.post('/api/planning/plans', headers=headers, json={
            'name': '全学院周期', 'start_date': '2026-02-02', 'weeks': 20,
            'deadline': '2026-01-31T23:59:59', 'global_cycle': True, 'term': 2,
            'rule_confirmed': True})
        self.assertEqual(response.status_code, 200, response.text)
        plan = response.json()
        self.assertTrue(plan['global_cycle'])
        self.assertEqual(plan['academic_term'], 2)
        self.assertNotIn('major', plan)
        # 未指定教学组时自动纳入全部班级。
        self.assertEqual(set(plan['groups']), {'视传2401', '视传2501', '插画2501'})

        generated = await self.client.post(f"/api/planning/plans/{plan['id']}/generate", headers=headers)
        self.assertEqual(generated.status_code, 200, generated.text)
        self.assertEqual(generated.json()['added'], 3)

        state = (await self.client.get(f"/api/planning/plans/{plan['id']}", headers=headers)).json()
        self.assertEqual({(task['major'], task['cohort'], task['group']) for task in state['tasks']}, {
            ('视觉传达设计', '2024', '视传2401'),
            ('视觉传达设计', '2025', '视传2501'),
            ('插画设计', '2025', '插画2501'),
        })
        # 2024 级在 2025—2026 学年第二学期为第4培养学期，2025 级为第2学期。
        self.assertEqual({task['program_semester'] for task in state['tasks']}, {2, 4})

        pool = (await self.client.get(f"/api/planning/plans/{plan['id']}/course-pool", headers=headers)).json()
        self.assertTrue(pool['global_cycle'])
        self.assertEqual(len(pool['document_ids']), 3)
        self.assertEqual({course['major'] for course in pool['courses']}, {'视觉传达设计', '插画设计'})

        again = await self.client.post(f"/api/planning/plans/{plan['id']}/generate", headers=headers)
        self.assertEqual(again.json()['added'], 0)
