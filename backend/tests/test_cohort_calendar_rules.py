import unittest
import test_debug_mode
from datetime import date, datetime
from app.models.class_info import ClassInfo
from app.models.planning import AcademicPlan, CohortCalendarRule, TeachingTask, MatchRun, TeachingAssignment, PublishedPlan, PeriodSlot
from app.services.stage_planning import occurrences, capacity
from app.api.planning import assigned_tasks
from app.services.cohort_calendar import cohort_exam_weeks
from app.services.course_catalog import course_catalog_scope
from app.models.course import Course


class CohortCalendarRuleTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown = test_debug_mode.DebugModeTests.asyncTearDown

    async def test_admin_can_save_global_grade_calendar_and_plan_api_reflects_it(self):
        headers = {'Authorization': 'Bearer ' + (await self.client.post(
            '/api/debug/session', json={'role': 'admin'})).json()['access_token']}
        self.db.add_all([
            ClassInfo(name='视传2601', grade='2026', department='视觉传达设计', student_count=30),
            ClassInfo(name='包装2601', grade='2026', department='包装设计', student_count=30),
        ])
        self.db.add(AcademicPlan(id=1, name='全学院秋季周期', start_date=date(2026, 9, 7), weeks=20,
                                 deadline=datetime(2026, 8, 1), state='draft', revision=1,
                                 settings={'groups': ['视传2601', '包装2601']}))
        self.db.commit()
        response = await self.client.put('/api/planning/calendar-rules/2026', headers=headers, json={
            'weeks': 18, 'start_date': '2026-09-14', 'exam_weeks': [18],
        })
        self.assertEqual(response.status_code, 200, response.text)
        listing = await self.client.get('/api/planning/calendar-rules', headers=headers)
        row = next(item for item in listing.json() if item['cohort'] == '2026')
        self.assertEqual(row['weeks'], 18)
        self.assertEqual(row['start_date'], '2026-09-14')
        self.assertEqual(row['exam_weeks'], [18])
        state = await self.client.get('/api/planning/plans/1', headers=headers)
        self.assertEqual(state.status_code, 200, state.text)
        self.assertEqual(state.json()['cohort_calendar_rules']['2026']['weeks'], 18)

    async def test_grade_rule_rejects_non_monday_and_invalid_exam_week(self):
        headers = {'Authorization': 'Bearer ' + (await self.client.post(
            '/api/debug/session', json={'role': 'admin'})).json()['access_token']}
        invalid_date = await self.client.put('/api/planning/calendar-rules/2026', headers=headers, json={
            'weeks': 18, 'start_date': '2026-09-15', 'exam_weeks': [18],
        })
        self.assertEqual(invalid_date.status_code, 422)
        invalid_week = await self.client.put('/api/planning/calendar-rules/2026', headers=headers, json={
            'weeks': 18, 'start_date': '2026-09-14', 'exam_weeks': [19],
        })
        self.assertEqual(invalid_week.status_code, 422)

    async def test_grade_calendar_controls_actual_dates_and_rejects_overflow(self):
        self.db.add(ClassInfo(name='视传2601', grade='2026', department='视觉传达设计', student_count=30))
        plan = AcademicPlan(id=3, name='跨专业周期', start_date=date(2026, 9, 7), weeks=20,
            deadline=datetime(2026, 8, 1), state='draft', revision=1, settings={})
        self.db.add(plan)
        self.db.add(CohortCalendarRule(cohort='2026', weeks=18, start_date=date(2026, 9, 14), exam_weeks=[18]))
        task = {'cohort': '2026', 'group': '视传2601', 'start_week': 2, 'end_week': 2,
                'slots': [{'day': 3, 'start': 1, 'count': 2}]}
        self.db.commit()
        self.assertEqual(list(occurrences(task, plan, self.db))[0][1], date(2026, 9, 23))
        self.assertEqual(cohort_exam_weeks(self.db, plan, '2026级'), {18})
        headers = {'Authorization': 'Bearer ' + (await self.client.post(
            '/api/debug/session', json={'role': 'admin'})).json()['access_token']}
        response = await self.client.put('/api/planning/calendar-rules/2026', headers=headers, json={
            'weeks': 18, 'start_date': '2026-09-14', 'exam_weeks': [2],
        })
        self.assertEqual(response.status_code, 200, response.text)

    async def test_rule_update_refuses_to_invalidate_existing_course_span(self):
        headers = {'Authorization': 'Bearer ' + (await self.client.post(
            '/api/debug/session', json={'role': 'admin'})).json()['access_token']}
        self.db.add(ClassInfo(name='视传2601', grade='2026级', department='视觉传达设计', student_count=30))
        self.db.add(AcademicPlan(id=4, name='周期', start_date=date(2026, 9, 7), weeks=20,
            deadline=datetime(2026, 8, 1), state='draft', revision=1, settings={'groups': ['视传2601']}))
        self.db.add(TeachingTask(id=40, plan_id=4, payload={'name': '字体设计', 'group': '视传2601',
            'cohort': '2026级', 'start_week': 17, 'end_week': 19, 'code': 'C1'}))
        self.db.commit()
        response = await self.client.put('/api/planning/calendar-rules/2026', headers=headers, json={
            'weeks': 18, 'start_date': '2026-09-14', 'exam_weeks': [18],
        })
        self.assertEqual(response.status_code, 409, response.text)

    async def test_course_pool_uses_grade_start_date_for_curriculum_semester(self):
        self.db.add(ClassInfo(name='视传2401', grade='2024级', department='Design', student_count=30))
        self.db.add(Course(name='高级课程', course_code='C7', credits=2, total_hours=32, semester=7,
            cohort='2024', department='Design', teaching_weeks=8))
        self.db.commit()
        scope = course_catalog_scope(self.db, date(2027, 2, 1), 1,
            start_dates_by_cohort={'2024': date(2027, 9, 6)})
        self.assertEqual(len(scope), 1)
        self.assertEqual(scope[0]['semester'], 7)
        self.assertEqual([course.course_code for course in scope[0]['courses']], ['C7'])

    async def test_published_teacher_conflicts_follow_frozen_grade_dates(self):
        rule = CohortCalendarRule(cohort='2026', weeks=18, start_date=date(2026, 9, 14), exam_weeks=[])
        candidate_plan = AcademicPlan(id=10, name='候选周期', start_date=date(2026, 1, 5), weeks=18,
            deadline=datetime(2025, 12, 1), state='draft', revision=1, settings={})
        published_plan = AcademicPlan(id=11, name='已发布周期', start_date=date(2026, 6, 1), weeks=18,
            deadline=datetime(2026, 5, 1), state='published', revision=1, settings={})
        self.db.add_all([rule, candidate_plan, published_plan])
        self.db.flush()
        self.db.add(MatchRun(id=1, plan_id=11, payload={}))
        self.db.add(TeachingTask(id=110, plan_id=11, payload={'name': '已发布课程', 'code': 'OLD',
            'group': '视传2601', 'cohort': '2026', 'start_week': 1, 'end_week': 1,
            'slots': [{'day': 1, 'start': 1, 'count': 2}]}))
        self.db.add(PeriodSlot(task_id=110, day=1, start=1, count=2, phase='normal'))
        self.db.add(TeachingAssignment(task_id=110, teacher_ids=[7], match_id=1, locked=True))
        self.db.add(PublishedPlan(id=1, plan_id=11, payload={'plan': {'id': 11, 'start_date': '2026-06-01',
            'weeks': 18, 'cohort_calendar_rules': {'2026': {'weeks': 18, 'start_date': '2026-09-14', 'exam_weeks': []}}},
            'tasks': []}))
        self.db.commit()
        selected = assigned_tasks(self.db, candidate_plan, 7)
        candidate = {'name': '候选课程', 'code': 'NEW', 'group': '视传2601', 'cohort': '2026',
            'start_week': 1, 'end_week': 1, 'slots': [{'day': 1, 'start': 1, 'count': 2}]}
        reasons, _ = capacity(self.db, candidate_plan, candidate, 7,
            {'weekly_limit': 20, 'external_hours': {}, 'course_limit': 3}, selected)
        self.assertIn('教师实际授课节次冲突', reasons)
