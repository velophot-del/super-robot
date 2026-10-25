import unittest

import test_department_review
import test_department_schedule_review
from app.models.planning import (AcademicPlan, PeriodSlot, PlanningEvent,
                                 PreferenceSubmission, TeachingAssignment)
from app.services import department_review


class ManualTeacherAssignmentTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_department_schedule_review.DepartmentScheduleReviewTests.asyncSetUp
    asyncTearDown = test_department_schedule_review.DepartmentScheduleReviewTests.asyncTearDown
    headers = test_department_schedule_review.DepartmentScheduleReviewTests.headers
    plan = test_department_schedule_review.DepartmentScheduleReviewTests.plan
    task = test_department_schedule_review.DepartmentScheduleReviewTests.task
    prepare = test_department_schedule_review.DepartmentScheduleReviewTests.prepare
    propose = test_department_schedule_review.DepartmentScheduleReviewTests.propose

    async def test_unclaimed_course_has_scoped_teacher_pool_and_director_can_propose(self):
        pid, tasks, admin, teacher, director, _ = await self.prepare()
        task_id = tasks['Design A']
        url = f'/api/planning/plans/{pid}/tasks/{task_id}/review-options'
        scoped = await self.client.get(url, headers=director)
        self.assertEqual(scoped.status_code, 200, scoped.text)
        self.assertEqual([row['teacher_id'] for row in scoped.json()['teachers']], [7])
        self.assertEqual(scoped.json()['teachers'][0]['review_status'], 'unsubmitted')
        self.assertTrue(scoped.json()['can_assign'])
        all_teachers = await self.client.get(url, headers=admin)
        self.assertEqual({row['teacher_id'] for row in all_teachers.json()['teachers']}, {7, 8, 9})
        self.assertEqual((await self.client.get(url, headers=teacher)).status_code, 403)
        proposal_id = await self.propose(pid, task_id, director, changes={'reason': ''})
        self.assertIsNone(self.db.get(TeachingAssignment, task_id))
        sent = await self.client.post(
            f'/api/planning/plans/{pid}/tasks/{task_id}/department-schedule-submit',
            headers=director, json={'proposal_id': proposal_id})
        self.assertEqual(sent.status_code, 200, sent.text)
        confirmed = await self.client.post(
            f'/api/planning/plans/{pid}/tasks/{task_id}/department-schedule-decision',
            headers=admin, json={'proposal_id': proposal_id, 'approved': True, 'reason': '指定任课'})
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertEqual(self.db.get(TeachingAssignment, task_id).teacher_ids, [7])
        self.assertEqual(self.db.query(PreferenceSubmission).count(), 0)
        self.assertEqual(self.db.get(AcademicPlan, pid).state, 'open')

    async def test_all_manual_allocations_can_match_and_publish_without_submissions(self):
        pid, tasks, admin, _, _, _ = await self.prepare()
        for day, (group, task_id) in enumerate(tasks.items(), 1):
            self.db.add(PeriodSlot(task_id=task_id, day=day, start=1, count=4, phase='normal'))
        self.db.commit()
        for group, task_id in tasks.items():
            teacher_id = 9 if group.startswith('Packaging') else 7
            saved = await self.client.put(
                f'/api/planning/plans/{pid}/tasks/{task_id}/assignment', headers=admin,
                json={'teacher_ids': [teacher_id]})
            self.assertEqual(saved.status_code, 200, saved.text)
        matched = await self.client.post(f'/api/planning/plans/{pid}/match', headers=admin)
        self.assertEqual(matched.status_code, 200, matched.text)
        published = await self.client.post(f'/api/planning/plans/{pid}/publish', headers=admin)
        self.assertEqual(published.status_code, 200, published.text)
        self.assertEqual(self.db.query(PreferenceSubmission).count(), 0)
        self.assertEqual(self.db.query(PlanningEvent).filter_by(action='manual_teacher_assignment').count(), 4)
        denied = await self.client.put(
            f'/api/planning/plans/{pid}/tasks/{tasks["Design A"]}/assignment', headers=admin,
            json={'teacher_ids': [9]})
        self.assertEqual(denied.status_code, 409)

    async def test_manual_allocation_keeps_scope_recusal_and_stale_write_guards(self):
        pid, tasks, admin, teacher, director, _ = await self.prepare()
        task_id = tasks['Design A']
        board = (await self.client.get(f'/api/planning/plans/{pid}/department-schedule', headers=director)).json()
        row = next(row for row in board['tasks'] if row['id'] == task_id)
        draft_url = f'/api/planning/plans/{pid}/tasks/{task_id}/department-schedule-draft'
        for forbidden_id in [8, 9]:
            response = await self.client.put(draft_url, headers=director, json={
                'base_revision': row['plan_revision'], 'base_fingerprint': row['base_fingerprint'],
                'teacher_ids': [forbidden_id]})
            self.assertEqual(response.status_code, 403, response.text)
        url = f'/api/planning/plans/{pid}/tasks/{task_id}/assignment'
        self.assertEqual((await self.client.put(url, headers=teacher, json={'teacher_ids': [7]})).status_code, 403)
        options = (await self.client.get(url.replace('/assignment', '/review-options'), headers=admin)).json()
        data = {'teacher_ids': [7], 'base_revision': options['base_revision'],
                'base_fingerprint': options['base_fingerprint']}
        self.assertEqual((await self.client.put(url, headers=admin, json=data)).status_code, 200)
        stale = await self.client.put(url, headers=admin, json={**data, 'teacher_ids': [9]})
        self.assertEqual(stale.status_code, 409, stale.text)
        self.assertEqual(self.db.get(TeachingAssignment, task_id).teacher_ids, [7])

    async def test_open_manual_assignments_reserve_teacher_periods(self):
        pid, tasks, admin, _, _, _ = await self.prepare()
        for task_id in [tasks['Design A'], tasks['Design B']]:
            self.db.add(PeriodSlot(task_id=task_id, day=1, start=1, count=4, phase='normal'))
        self.db.commit()
        for group, expected in [('Design A', 200), ('Design B', 409)]:
            result = await self.client.put(
                f'/api/planning/plans/{pid}/tasks/{tasks[group]}/assignment', headers=admin,
                json={'teacher_ids': [7]})
            self.assertEqual(result.status_code, expected, result.text)
        self.assertIsNone(self.db.get(TeachingAssignment, tasks['Design B']))
        other_plan = await self.plan()
        created = await self.client.post(f'/api/planning/plans/{other_plan}/tasks', headers=admin,
            json={**self.task('OTHER'), 'group': 'Other class'})
        other_task = created.json()['id']
        self.assertEqual((await self.client.post(f'/api/planning/plans/{other_plan}/open', headers=admin)).status_code, 200)
        conflict = await self.client.put(
            f'/api/planning/plans/{other_plan}/tasks/{other_task}/assignment', headers=admin,
            json={'teacher_ids': [7]})
        self.assertEqual(conflict.status_code, 409, conflict.text)

    async def test_manual_source_does_not_forge_or_approve_pending_application(self):
        pid, task_id, submission_id, admin, _, _ = await test_department_review.DepartmentReviewTests.prepare(self)
        saved = await self.client.put(f'/api/planning/plans/{pid}/tasks/{task_id}/assignment',
            headers=admin, json={'teacher_ids': [7]})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(department_review.status(self.db, self.db.get(AcademicPlan, pid),
            self.db.get(PreferenceSubmission, submission_id), task_id), 'pending')
        self.assertEqual((await self.client.post(f'/api/planning/plans/{pid}/match', headers=admin)).status_code, 200)
        published = await self.client.post(f'/api/planning/plans/{pid}/publish', headers=admin)
        self.assertEqual(published.status_code, 200, published.text)

    async def test_director_can_directly_assign_unclaimed_in_scope_course(self):
        pid, tasks, _, _, director, _ = await self.prepare()
        task_id = tasks['Design A']
        url = f'/api/planning/plans/{pid}/tasks/{task_id}/assignment'
        options = (await self.client.get(url.replace('/assignment', '/review-options'),
                                         headers=director)).json()
        self.assertFalse(options['has_applications'])
        self.assertTrue(options['can_direct_assign'])
        saved = await self.client.put(url, headers=director, json={
            'teacher_ids': [7], 'base_revision': options['base_revision'],
            'base_fingerprint': options['base_fingerprint']})
        self.assertEqual(saved.status_code, 200, saved.text)
        assignment = self.db.get(TeachingAssignment, task_id)
        self.assertEqual(assignment.teacher_ids, [7])
        self.assertTrue(assignment.locked)
        record = self.db.query(PlanningEvent).filter_by(
            action='manual_teacher_assignment').one()
        self.assertEqual(record.payload['source'], 'department_director')
        self.assertEqual(self.db.query(PreferenceSubmission).count(), 0)
        board = (await self.client.get(
            f'/api/planning/plans/{pid}/department-schedule', headers=director)).json()
        row = next(item for item in board['tasks'] if item['id'] == task_id)
        self.assertEqual(row['teacher_names'], ['Demo teacher'])
        self.assertTrue(row['can_edit_department_schedule'])

    async def test_director_direct_assignment_scope_recusal_and_claim_guards(self):
        pid, tasks, admin, teacher, director, other_director = await self.prepare()
        task_id = tasks['Design A']
        claimed_id = tasks['Design B']
        plan = self.db.get(AcademicPlan, pid)
        self.db.add(PreferenceSubmission(plan_id=pid, teacher_id=7,
            plan_revision=plan.revision, draft_revision=1, task_ids=[claimed_id]))
        self.db.commit()
        url = f'/api/planning/plans/{pid}/tasks/{task_id}/assignment'
        claimed_url = f'/api/planning/plans/{pid}/tasks/{claimed_id}/assignment'
        self.assertEqual((await self.client.put(claimed_url, headers=director,
            json={'teacher_ids': [7]})).status_code, 403)
        self.assertEqual((await self.client.put(url, headers=other_director,
            json={'teacher_ids': [9]})).status_code, 403)
        self.assertEqual((await self.client.put(url, headers=director,
            json={'teacher_ids': [8]})).status_code, 403)
        self.assertEqual((await self.client.put(url, headers=director,
            json={'teacher_ids': [9]})).status_code, 403)
        self.assertEqual((await self.client.put(url, headers=teacher,
            json={'teacher_ids': [7]})).status_code, 403)
        saved = await self.client.put(url, headers=admin, json={'teacher_ids': [7]})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual((await self.client.put(url, headers=director,
            json={'teacher_ids': [7]})).status_code, 403)

    async def test_director_direct_assignments_survive_match_and_publish(self):
        pid, tasks, admin, _, director, _ = await self.prepare()
        for day, task_id in enumerate(tasks.values(), 1):
            self.db.add(PeriodSlot(task_id=task_id, day=day, start=1, count=4,
                                   phase='normal'))
        self.db.commit()
        for group, task_id in tasks.items():
            headers = director if group.startswith('Design') else admin
            teacher_id = 9 if group.startswith('Packaging') else 7
            saved = await self.client.put(
                f'/api/planning/plans/{pid}/tasks/{task_id}/assignment',
                headers=headers, json={'teacher_ids': [teacher_id]})
            self.assertEqual(saved.status_code, 200, saved.text)
        matched = await self.client.post(f'/api/planning/plans/{pid}/match', headers=admin)
        self.assertEqual(matched.status_code, 200, matched.text)
        published = await self.client.post(f'/api/planning/plans/{pid}/publish', headers=admin)
        self.assertEqual(published.status_code, 200, published.text)
        self.assertEqual(self.db.query(PreferenceSubmission).count(), 0)
        events = self.db.query(PlanningEvent).filter_by(
            action='manual_teacher_assignment').all()
        self.assertEqual(len(events), 4)
        self.assertEqual({event.payload['source'] for event in events},
                         {'administrator', 'department_director'})
