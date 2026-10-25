import unittest
import test_debug_mode
from datetime import date
from app.models.class_info import ClassInfo
from app.models.planning import AcademicPlan, CohortCalendarRule, TeachingTask
from app.models.course import Course
from app.services.academic_scope import cohort_matches, department_matches, grade_label, program_semester


class GlobalPlanCycleTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown = test_debug_mode.DebugModeTests.asyncTearDown

    async def test_department_scope_requires_exact_major_name(self):
        self.assertTrue(department_matches('视觉传达设计', '视觉传达设计'))
        self.assertFalse(department_matches('视觉传达设计', '视觉传达设计（中外合作）'))
        self.assertTrue(department_matches('视觉传达设计,插画设计', '插画设计'))

    async def test_global_cycle_generates_all_majors_and_cohorts(self):
        headers = {'Authorization': 'Bearer ' + (
            await self.client.post('/api/debug/session', json={'role': 'admin'})).json()['access_token']}
        for name, grade, department in [('视传2401', '2024', '视觉传达设计'),
                                        ('视传2501', '2025', '视觉传达设计'),
                                        ('视传2502', '2025', '视觉传达设计'),
                                        ('插画2501', '2025', '插画设计')]:
            self.db.add(ClassInfo(name=name, grade=grade, department=department, student_count=30))
        self.db.add(ClassInfo(name='停用班级', grade='2025', department='视觉传达设计',
                              student_count=30, is_active=False))

        self.db.add_all([
            Course(name='设计基础', course_code='D24', credits=2, total_hours=32, semester=4,
                   cohort='2024', department='视觉传达设计', teaching_weeks=4),
            Course(name='版式设计', course_code='D25', credits=2, total_hours=32, semester=2,
                   cohort='2025', department='视觉传达设计', teaching_weeks=4),
            Course(name='插画基础', course_code='I25', credits=2, total_hours=32, semester=2,
                   cohort='2025', department='插画设计', teaching_weeks=4),
        ])
        self.db.commit()

        response = await self.client.post('/api/planning/plans', headers=headers, json={
            'name': '全学院周期', 'start_date': '2026-02-02', 'weeks': 20,
            'deadline': '2026-01-31T23:59:59', 'global_cycle': True, 'term': 2,
            'groups': ['视传2401'],
            'rule_confirmed': True})
        self.assertEqual(response.status_code, 200, response.text)
        plan = response.json()
        self.assertTrue(plan['global_cycle'])
        self.assertEqual(plan['academic_term'], 2)
        self.assertNotIn('major', plan)
        # 全学院周期忽略旧客户端的局部班级范围，纳入全部有效班级并排除停用班级。
        self.assertEqual(set(plan['groups']), {'视传2401', '视传2501', '视传2502', '插画2501'})

        generated = await self.client.post(f"/api/planning/plans/{plan['id']}/generate", headers=headers)
        self.assertEqual(generated.status_code, 200, generated.text)
        self.assertEqual(generated.json()['added'], 4)

        state = (await self.client.get(f"/api/planning/plans/{plan['id']}", headers=headers)).json()
        self.assertEqual({(task['major'], task['cohort'], task['group']) for task in state['tasks']}, {
            ('视觉传达设计', '2024', '视传2401'),
            ('视觉传达设计', '2025', '视传2501'),
            ('视觉传达设计', '2025', '视传2502'),
            ('插画设计', '2025', '插画2501'),
        })
        # 周期从2026年2月开始，按周期日期为第二学期；2024届为第4学期、2025届为第2学期。
        self.assertEqual({task['program_semester'] for task in state['tasks']}, {2, 4})

        pool = (await self.client.get(f"/api/planning/plans/{plan['id']}/course-pool", headers=headers)).json()
        self.assertTrue(pool['global_cycle'])
        self.assertEqual(pool['document_ids'], [])
        self.assertEqual({course['major'] for course in pool['courses']}, {'视觉传达设计', '插画设计'})

        again = await self.client.post(f"/api/planning/plans/{plan['id']}/generate", headers=headers)
        self.assertEqual(again.json()['added'], 0)

    async def test_march_2027_cycle_uses_2026_cohort_second_semester_courses(self):
        headers = {'Authorization': 'Bearer ' + (
            await self.client.post('/api/debug/session', json={'role': 'admin'})).json()['access_token']}
        self.db.add(ClassInfo(name='视传2601', grade='2026', department='视觉传达设计', student_count=30))

        self.db.add_all([
            Course(name='第一学期课程', course_code='D1', credits=2, total_hours=32, semester=1,
                   cohort='2026', department='视觉传达设计', teaching_weeks=4),
            Course(name='第二学期课程', course_code='D2', credits=2, total_hours=32, semester=2,
                   cohort='2026', department='视觉传达设计', teaching_weeks=4),
        ])
        self.db.commit()

        created = await self.client.post('/api/planning/plans', headers=headers, json={
            'name': '2026-2027-2学期', 'start_date': '2027-03-01', 'weeks': 20,
            'deadline': '2027-02-28T23:59:59', 'global_cycle': True, 'term': 2,
            'rule_confirmed': True})
        self.assertEqual(created.status_code, 200, created.text)
        plan = created.json()
        self.assertEqual(plan['academic_term'], 2)

        generated = await self.client.post(f"/api/planning/plans/{plan['id']}/generate", headers=headers)
        self.assertEqual(generated.status_code, 200, generated.text)
        self.assertEqual(generated.json()['added'], 1)
        state = (await self.client.get(f"/api/planning/plans/{plan['id']}", headers=headers)).json()
        self.assertEqual([(task['name'], task['program_semester']) for task in state['tasks']], [('第二学期课程', 2)])

        overridden = await self.client.post('/api/planning/plans', headers=headers, json={
            'name': '手动设为上学期', 'start_date': '2027-03-01', 'weeks': 20,
            'deadline': '2027-02-28T23:59:59', 'global_cycle': True, 'term': 1,
            'rule_confirmed': True})
        self.assertEqual(overridden.status_code, 200, overridden.text)
        self.assertEqual(overridden.json()['academic_term'], 1)
        generate_override = await self.client.post(
            f"/api/planning/plans/{overridden.json()['id']}/generate", headers=headers)
        self.assertEqual(generate_override.status_code, 200, generate_override.text)
        override_state = (await self.client.get(
            f"/api/planning/plans/{overridden.json()['id']}", headers=headers)).json()
        self.assertEqual([(task['name'], task['program_semester']) for task in override_state['tasks']], [('第一学期课程', 1)])

    async def test_august_2027_cycle_catalog_and_ai_use_cycle_date_despite_old_calendar_dates(self):
        headers = {'Authorization': 'Bearer ' + (
            await self.client.post('/api/debug/session', json={'role': 'admin'})).json()['access_token']}
        self.db.add_all([
            ClassInfo(name='视传2601', grade='2026', department='视觉传达设计', student_count=30),
            ClassInfo(name='视传2301', grade='2023', department='视觉传达设计', student_count=30),
            CohortCalendarRule(cohort='2026', weeks=20, start_date=date(2026, 8, 31), exam_weeks=[20]),
            CohortCalendarRule(cohort='2023', weeks=20, start_date=date(2023, 8, 28), exam_weeks=[20]),
            Course(name='第一学期课程', course_code='D1', credits=2, total_hours=32, semester=1,
                   cohort='2026', department='视觉传达设计', teaching_weeks=4),
            Course(name='第三学期课程', course_code='D3', credits=2, total_hours=32, semester=3,
                   cohort='2026', department='视觉传达设计', teaching_weeks=4),
        ])
        self.db.commit()

        created = await self.client.post('/api/planning/plans', headers=headers, json={
            'name': '2027-2028-1学期', 'start_date': '2027-08-30', 'weeks': 20,
            'deadline': '2027-08-20T23:59:59', 'global_cycle': True, 'term': 1,
            'rule_confirmed': True})
        self.assertEqual(created.status_code, 200, created.text)
        plan = created.json()
        self.assertEqual(plan['groups'], ['视传2601'])

        pool = await self.client.get(f"/api/planning/plans/{plan['id']}/course-pool", headers=headers)
        self.assertEqual(pool.status_code, 200, pool.text)
        self.assertEqual([(course['name'], course['semester']) for course in pool.json()['courses']], [('第三学期课程', 3)])

        state = (await self.client.get(f"/api/planning/plans/{plan['id']}", headers=headers)).json()
        filled = await self.client.post(f"/api/planning/plans/{plan['id']}/auto-fill/ai", headers=headers,
            json={'revision': state['revision']})
        self.assertEqual(filled.status_code, 200, filled.text)
        self.assertEqual([(task['course'], task['semester']) for task in filled.json()['placed']], [('第三学期课程', 3)])
        state = (await self.client.get(f"/api/planning/plans/{plan['id']}", headers=headers)).json()
        self.assertEqual([(task['name'], task['program_semester']) for task in state['tasks']], [('第三学期课程', 3)])

        generated_plan = await self.client.post('/api/planning/plans', headers=headers, json={
            'name': '2027-2028-1学期生成验证', 'start_date': '2027-08-30', 'weeks': 20,
            'deadline': '2027-08-20T23:59:59', 'global_cycle': True, 'term': 1,
            'rule_confirmed': True})
        self.assertEqual(generated_plan.status_code, 200, generated_plan.text)
        generated = await self.client.post(
            f"/api/planning/plans/{generated_plan.json()['id']}/generate", headers=headers)
        self.assertEqual(generated.status_code, 200, generated.text)
        generated_state = (await self.client.get(
            f"/api/planning/plans/{generated_plan.json()['id']}", headers=headers)).json()
        self.assertEqual([(task['name'], task['program_semester']) for task in generated_state['tasks']], [('第三学期课程', 3)])

    async def test_course_pool_excludes_graduated_grade_past_curriculum_end(self):
        self.assertTrue(cohort_matches('2021级', '21'))
        self.assertEqual(program_semester('2027-03-08', 2, '21级'), 12)
        self.assertEqual(grade_label('21届'), '21级')
        headers = {'Authorization': 'Bearer ' + (
            await self.client.post('/api/debug/session', json={'role': 'admin'})).json()['access_token']}

        self.db.add_all([
            ClassInfo(name='视传2101', grade='2021', department='视觉传达设计', student_count=30),
            ClassInfo(name='视传2201', grade='2022', department='视觉传达设计', student_count=30),
            ClassInfo(name='视传2401', grade='2024', department='视觉传达设计', student_count=30),
            Course(name='G21-8', course_code='G21-8', total_hours=32, credits=2, semester=8,
                   cohort='2021', department='视觉传达设计'),
            Course(name='G24-6', course_code='G24-6', total_hours=32, credits=2, semester=6,
                   cohort='2024', department='视觉传达设计'),
        ])
        self.db.commit()
        self.db.commit()
        created = await self.client.post('/api/planning/plans', headers=headers, json={
            'name': '2026-2027-2学期', 'start_date': '2027-03-08', 'weeks': 20,
            'deadline': '2027-03-01T23:59:59', 'global_cycle': True, 'term': 2,
            'rule_confirmed': True})
        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(created.json()['groups'], ['视传2401'])
        rejected = await self.client.put(f"/api/planning/plans/{created.json()['id']}/groups", headers=headers,
            json={'revision': created.json()['revision'], 'groups': ['视传2401', '视传2101']})
        self.assertEqual(rejected.status_code, 422, rejected.text)

        # Older cycles may contain a previously snapshotted roster; hide graduated groups on read.
        saved_plan = self.db.get(AcademicPlan, created.json()['id'])
        saved_plan.settings = {**saved_plan.settings, 'groups': ['视传2101', '视传2201', '视传2401']}
        self.db.add(TeachingTask(plan_id=saved_plan.id, payload={
            'group': '视传2101', 'name': '旧年级课程', 'room_id': None, 'student_count': 0,
        }))
        self.db.commit()
        state = await self.client.get(f"/api/planning/plans/{created.json()['id']}", headers=headers)
        self.assertEqual(state.status_code, 200, state.text)
        self.assertEqual(state.json()['groups'], ['视传2401'])
        self.assertEqual(state.json()['tasks'], [])
        saved_plan.state = 'open'
        self.db.commit()
        opened_state = await self.client.get(f"/api/planning/plans/{created.json()['id']}", headers=headers)
        self.assertEqual(opened_state.status_code, 200, opened_state.text)
        self.assertEqual(opened_state.json()['groups'], ['视传2401'])
        self.assertEqual(opened_state.json()['tasks'], [])
        saved_plan.state = 'published'
        self.db.commit()
        historical_state = await self.client.get(f"/api/planning/plans/{created.json()['id']}", headers=headers)
        self.assertEqual(historical_state.status_code, 200, historical_state.text)
        self.assertEqual(historical_state.json()['groups'], ['视传2101', '视传2201', '视传2401'])
        self.assertEqual([task['group'] for task in historical_state.json()['tasks']], ['视传2101'])

        pool = await self.client.get(f"/api/planning/plans/{created.json()['id']}/course-pool", headers=headers)
        self.assertEqual(pool.status_code, 200, pool.text)
        self.assertEqual(pool.json()['document_ids'], [])
        self.assertEqual({course['cohort'] for course in pool.json()['courses']}, {'2024'})
