import unittest
from copy import deepcopy
from datetime import date

import test_department_schedule_review
import test_schedule_change
from app.api.planning import assigned_tasks
from app.models.planning import (AcademicPlan, CohortCalendarRule, MatchRun,
    PeriodSlot, PlanningEvent, PreferenceSubmission, PublishedPlan, TeachingAssignment, TeachingTask)
from app.services.cohort_calendar import cohort_start_date, cohort_exam_weeks
from app.services.plan_versions import superseded_plan_ids


class ReviewRegressionTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_department_schedule_review.DepartmentScheduleReviewTests.asyncSetUp
    asyncTearDown = test_department_schedule_review.DepartmentScheduleReviewTests.asyncTearDown
    headers = test_department_schedule_review.DepartmentScheduleReviewTests.headers
    plan = test_department_schedule_review.DepartmentScheduleReviewTests.plan
    task = test_department_schedule_review.DepartmentScheduleReviewTests.task
    prepare = test_department_schedule_review.DepartmentScheduleReviewTests.prepare
    propose = test_department_schedule_review.DepartmentScheduleReviewTests.propose
    async def test_selection_hides_private_payload_but_keeps_public_courses(self):
        pid, ids, admin, teacher, _, _ = await self.prepare()
        task = self.db.get(TeachingTask, ids['Design A'])
        task.payload = {**task.payload, 'student_ids': ['PRIVATE-STUDENT'],
            'source': {'course_id': 12, 'major': 'Design', 'private': 'PRIVATE-SOURCE'}}
        self.db.commit()
        response = await self.client.get(f'/api/planning/plans/{pid}', headers=teacher)
        self.assertEqual(response.status_code, 200, response.text)
        row = next(t for t in response.json()['tasks'] if t['id'] == task.id)
        self.assertEqual(row['source']['course_id'], 12)
        self.assertNotIn('PRIVATE-', response.text)
        full = await self.client.get(f'/api/planning/plans/{pid}', headers=admin)
        self.assertIn('PRIVATE-STUDENT', full.text)

    async def test_claimed_course_proposal_requires_latest_approved_application(self):
        pid, ids, _, _, director, _ = await self.prepare()
        task_id = ids['Design A']
        sub = PreferenceSubmission(plan_id=pid, teacher_id=7,
            plan_revision=self.db.get(AcademicPlan, pid).revision, draft_revision=1,
            task_ids=[task_id])
        self.db.add(sub); self.db.commit()
        board = (await self.client.get(f'/api/planning/plans/{pid}/department-schedule', headers=director)).json()
        row = next(t for t in board['tasks'] if t['id'] == task_id)
        payload = {'teacher_ids': [7], 'base_revision': row['plan_revision'],
                   'base_fingerprint': row['base_fingerprint']}
        url = f'/api/planning/plans/{pid}/tasks/{task_id}/department-schedule-draft'
        self.assertEqual((await self.client.put(url, headers=director, json=payload)).status_code, 409)
        review_url = f'/api/planning/plans/{pid}/department-reviews'
        review = {'submission_id': sub.id, 'task_id': task_id, 'approved': True, 'reason': '资格核实'}
        self.assertEqual((await self.client.post(review_url, headers=director, json=review)).status_code, 200)
        self.assertEqual((await self.client.put(url, headers=director, json=payload)).status_code, 200)

    async def test_admin_confirmation_rechecks_application_after_proposal(self):
        pid, ids, admin, _, director, _ = await self.prepare()
        task_id = ids['Design A']
        sub = PreferenceSubmission(plan_id=pid, teacher_id=7,
            plan_revision=self.db.get(AcademicPlan, pid).revision, draft_revision=1,
            task_ids=[task_id])
        self.db.add(sub); self.db.commit()
        review = {'submission_id': sub.id, 'task_id': task_id, 'approved': True, 'reason': '资格核实'}
        await self.client.post(f'/api/planning/plans/{pid}/department-reviews', headers=director, json=review)
        proposal_id = await self.propose(pid, task_id, director)
        await self.client.post(f'/api/planning/plans/{pid}/tasks/{task_id}/department-schedule-submit',
            headers=director, json={'proposal_id': proposal_id})
        # A new immutable submission invalidates approval of the previous one.
        self.db.add(PreferenceSubmission(plan_id=pid, teacher_id=7,
            plan_revision=self.db.get(AcademicPlan, pid).revision, draft_revision=2, task_ids=[task_id]))
        self.db.commit()
        response = await self.client.post(f'/api/planning/plans/{pid}/tasks/{task_id}/department-schedule-decision',
            headers=admin, json={'proposal_id': proposal_id, 'approved': True, 'reason': '确认调剂'})
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIsNone(self.db.get(TeachingAssignment, task_id))

    async def test_department_confirmation_never_exempts_a_claimed_course_from_publication_review(self):
        from app.services import department_review, department_schedule_review
        pid, ids, _, _, _, _ = await self.prepare()
        task = self.db.get(TeachingTask, ids['Design A'])
        self.db.add(MatchRun(id=1, plan_id=pid, payload={})); self.db.flush()
        self.db.add(TeachingAssignment(task_id=task.id, teacher_ids=[7], match_id=1, locked=True))
        self.db.add(PreferenceSubmission(plan_id=pid, teacher_id=7,
            plan_revision=self.db.get(AcademicPlan, pid).revision, draft_revision=1, task_ids=[task.id]))
        self.db.add(PlanningEvent(plan_id=pid, actor='user:1', action='manual_teacher_assignment',
            payload={'task_id': task.id, 'match_id': 1, 'teacher_ids': [7],
                     'source': 'department_confirmation',
                     'task_payload': department_review.task_fingerprint(task.payload)}))
        self.db.commit()
        self.assertEqual(department_schedule_review.manual_teacher_ids(self.db, task), set())


class PublishedVersionRegressionTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_schedule_change.ScheduleChangeTests.asyncSetUp
    asyncTearDown = test_schedule_change.ScheduleChangeTests.asyncTearDown
    _published = test_schedule_change.ScheduleChangeTests._published
    _headers = test_schedule_change.ScheduleChangeTests._headers

    async def test_parallel_change_requests_cannot_fork_the_same_published_version(self):
        await self._published()
        teacher = await self._headers('teacher', 7)
        admin = await self._headers('admin')
        for index in range(2):
            request = await self.client.post('/api/planning/plans/1/change-requests', headers=teacher,
                json={'snapshot_id': 1, 'task_id': 1, 'reason': f'调整课程时间原因{index}'})
            self.assertEqual(request.status_code, 200, request.text)
            response = await self.client.post(
                f"/api/planning/plans/1/change-requests/{request.json()['request_id']}/decision",
                headers=admin, json={'approve': True})
            self.assertEqual(response.status_code, 200 if index == 0 else 409, response.text)
        self.assertEqual(self.db.query(AcademicPlan).count(), 2)

    async def test_stale_revision_branch_cannot_be_published(self):
        await self._published()
        original = self.db.get(AcademicPlan, 1)
        for plan_id, state in [(2, 'published'), (3, 'matched')]:
            self.db.add(AcademicPlan(id=plan_id, name='Revision', start_date=original.start_date,
                weeks=20, deadline=original.deadline, state=state, settings={'supersedes_plan_id': 1}))
        self.db.commit()
        response = await self.client.post('/api/planning/plans/3/publish', headers=await self._headers('admin'))
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn('修订', response.json()['detail'])
    async def test_published_replacement_releases_old_occupancy_and_personal_display(self):
        payload = await self._published()
        old = self.db.get(AcademicPlan, 1)
        replacement = AcademicPlan(id=2, name='Revision', start_date=old.start_date,
            weeks=20, deadline=old.deadline, state='draft', settings={'supersedes_plan_id': 1})
        self.db.add(replacement); self.db.flush()
        candidate = AcademicPlan(id=3, name='Other', start_date=old.start_date,
            weeks=20, deadline=old.deadline, settings={})
        self.db.add(candidate); self.db.commit()
        self.assertEqual([p.id for _, p in assigned_tasks(self.db, candidate, 7)], [1])
        replacement.state = 'published'
        task_payload = deepcopy(self.db.get(TeachingTask, 1).payload)
        self.db.add(TeachingTask(id=2, plan_id=2, payload=task_payload))
        self.db.add(MatchRun(id=2, plan_id=2, payload={})); self.db.flush()
        self.db.add(TeachingAssignment(task_id=2, teacher_ids=[7], match_id=2, locked=True))
        revised = deepcopy(payload); revised['plan']['id'] = 2
        revised['plan']['supersedes_plan_id'] = 1
        revised['tasks'][0].update(id=2, plan_id=2)
        self.db.add(PublishedPlan(id=2, plan_id=2, payload=revised)); self.db.commit()
        self.assertEqual([p.id for _, p in assigned_tasks(self.db, candidate, 7)], [2])
        headers = await self._headers('teacher', 7)
        result = await self.client.get('/api/my/planning-timetable', headers=headers)
        self.assertEqual([b['plan']['id'] for b in result.json()['batches']], [2])
        stale = await self.client.post('/api/planning/plans/1/confirm-schedule', headers=headers,
            json={'snapshot_id': 1, 'task_id': 1})
        self.assertEqual(stale.status_code, 409, stale.text)
        self.assertEqual(self.db.get(PublishedPlan, 1).payload, payload)

        # A third plan can use the room and Monday released by the old version.
        from app.api.planning import validate_global_room, validate_global_student_scope
        from app.models.classroom import Classroom
        from app.services.stage_planning import validate_tasks
        from app.services.auto_placement import _published_teacher_tasks
        self.db.add(Classroom(id=31, name='Room', room_code='R31', capacity=40))
        old_task = self.db.get(TeachingTask, 1)
        old_task.payload = {**old_task.payload, 'room_id': 31}
        self.db.add_all([PeriodSlot(task_id=1, day=1, start=1, count=1, phase='normal'),
                         PeriodSlot(task_id=2, day=2, start=1, count=1, phase='normal')])
        self.db.commit()
        course = {**task_payload, 'id': 999, 'code': 'OTHER', 'required_hours': 1, 'room_id': 31,
                  'slots': [{'day': 1, 'start': 1, 'count': 1, 'phase': 'normal'}]}
        validate_global_room(self.db, candidate, course, 31)
        validate_global_student_scope(self.db, candidate, course)
        validate_tasks(self.db, candidate, [course])
        self.assertEqual([p.id for _, p in _published_teacher_tasks(self.db, candidate)[7]], [2])

    async def test_replacement_chain_excludes_all_ancestors_only_after_publication(self):
        await self._published()
        old = self.db.get(AcademicPlan, 1)
        for plan_id, parent_id, state in [(2, 1, 'published'), (3, 2, 'draft')]:
            self.db.add(AcademicPlan(id=plan_id, name='Revision', start_date=old.start_date,
                weeks=20, deadline=old.deadline, state=state, settings={'supersedes_plan_id': parent_id}))
        self.db.commit()
        self.assertEqual(superseded_plan_ids(self.db), {1})
        self.db.get(AcademicPlan, 3).state = 'published'; self.db.commit()
        self.assertEqual(superseded_plan_ids(self.db), {1, 2})

    async def test_published_default_calendar_ignores_later_rule_creation(self):
        await self._published()
        plan = self.db.get(AcademicPlan, 1)
        self.db.add(CohortCalendarRule(cohort='2026', start_date=date(2027, 9, 6),
            weeks=18, exam_weeks=[18], revision=1)); self.db.commit()
        self.assertEqual(cohort_start_date(self.db, plan, '2026'), date(2027, 3, 1))
        self.assertEqual(cohort_exam_weeks(self.db, plan, '2026'), {20})
