import unittest
from datetime import datetime

import test_debug_mode
import test_planning_workflow
from app.models.class_info import ClassInfo
from app.models.planning import AcademicDirection, AcademicProgram, AcademicPlan, OfferingUnit, TeachingTask, PeriodSlot, TeachingAssignment, MatchRun
from app.models.teacher import Teacher


class DepartmentScheduleReviewTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown = test_debug_mode.DebugModeTests.asyncTearDown
    headers = test_planning_workflow.PlanningWorkflowTests.headers
    plan = test_planning_workflow.PlanningWorkflowTests.plan
    task = test_planning_workflow.PlanningWorkflowTests.task

    async def prepare(self):
        pid = await self.plan()
        admin = await self.headers()
        self.db.add_all([
            OfferingUnit(id=1, code='U1', name='Design unit'),
            OfferingUnit(id=2, code='U2', name='Packaging unit'),
            Teacher(id=8, name='Design director', teacher_code='T8', offering_unit_id=1,
                    position='教研室主任', review_major='Design'),
            Teacher(id=9, name='Packaging director', teacher_code='T9', offering_unit_id=2,
                    position='教研室主任', review_major='Packaging'),
        ])
        self.db.get(Teacher, 7).offering_unit_id = 1
        design = AcademicProgram(code='D-1', name='Design', duration_semesters=8)
        packaging = AcademicProgram(code='P-1', name='Packaging', duration_semesters=8)
        self.db.add_all([design, packaging]); self.db.flush()
        self.db.add_all([
            AcademicDirection(program_id=design.id, name='Design', offering_unit_id=1),
            AcademicDirection(program_id=packaging.id, name='Packaging', offering_unit_id=2),
            ClassInfo(name='Design A', grade='2026', department='Design', program_id=design.id, student_count=30),
            ClassInfo(name='Design B', grade='2026', department='Design', program_id=design.id, student_count=30),
            ClassInfo(name='Design C', grade='2026', department='Design', program_id=design.id, student_count=30),
            ClassInfo(name='Packaging A', grade='2026', department='Packaging', program_id=packaging.id, student_count=30),
        ])
        self.db.commit()
        task_ids = {}
        for group, major, code in [('Design A', 'Design', 'D-A'),
                                   ('Design B', 'Design', 'D-B'),
                                   ('Design C', 'Design', 'D-C'),
                                   ('Packaging A', 'Packaging', 'P-A')]:
            payload = {**self.task(code=code), 'group': group, 'class_name': group, 'department': major,
                       'slots': []}
            response = await self.client.post(f'/api/planning/plans/{pid}/tasks', headers=admin, json=payload)
            self.assertEqual(response.status_code, 200, response.text)
            task_ids[group] = response.json()['id']
        enabled = await self.client.post(f'/api/planning/plans/{pid}/enable-department-review', headers=admin)
        self.assertEqual(enabled.status_code, 200, enabled.text)
        opened = await self.client.post(f'/api/planning/plans/{pid}/open', headers=admin)
        self.assertEqual(opened.status_code, 200, opened.text)
        director = await self.client.post('/api/debug/session', json={'role': 'teacher', 'teacher_id': 8})
        other_director = await self.client.post('/api/debug/session', json={'role': 'teacher', 'teacher_id': 9})
        teacher = await self.headers('teacher')
        return pid, task_ids, admin, teacher, \
            {'Authorization': f"Bearer {director.json()['access_token']}"}, \
            {'Authorization': f"Bearer {other_director.json()['access_token']}"}

    async def propose(self, pid, task_id, director, board_row=None, changes=None):
        if board_row is None:
            board = await self.client.get(f'/api/planning/plans/{pid}/department-schedule', headers=director)
            self.assertEqual(board.status_code, 200, board.text)
            board_row = next(item for item in board.json()['tasks'] if item['id'] == task_id)
        payload = {'base_revision': board_row['plan_revision'], 'base_fingerprint': board_row['base_fingerprint'],
                   'teacher_ids': [7], 'reason': '教研室调剂建议'}
        payload.update(changes or {})
        response = await self.client.put(
            f'/api/planning/plans/{pid}/tasks/{task_id}/department-schedule-draft', headers=director,
            json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['proposal_id']

    async def test_board_includes_all_department_class_courses_without_other_unit_data(self):
        pid, task_ids, _, _, director, _ = await self.prepare()
        response = await self.client.get(f'/api/planning/plans/{pid}/department-schedule', headers=director)
        self.assertEqual(response.status_code, 200, response.text)
        rows = response.json()['tasks']
        self.assertEqual({row['group'] for row in rows}, {'Design A', 'Design B', 'Design C'})
        self.assertEqual({row['id'] for row in rows},
                         {task_ids['Design A'], task_ids['Design B'], task_ids['Design C']})
        self.assertTrue(all(row['applicants'] == [] for row in rows))
        self.assertNotIn('Packaging A', response.text)

    async def test_director_draft_does_not_mutate_official_task_or_assignment(self):
        pid, task_ids, admin, teacher, director, _ = await self.prepare()
        task_id = task_ids['Design A']
        state = (await self.client.get(f'/api/planning/plans/{pid}', headers=teacher)).json()
        design_task_ids = [tid for group, tid in task_ids.items() if group.startswith('Design')]
        draft = await self.client.put(f'/api/planning/plans/{pid}/draft', headers=teacher,
            json={'revision': 0, 'plan_revision': state['revision'], 'task_ids': design_task_ids})
        self.assertEqual(draft.status_code, 200, draft.text)
        submission = await self.client.post(f'/api/planning/plans/{pid}/submit', headers=teacher,
            json={'revision': draft.json()['revision']})
        self.assertEqual(submission.status_code, 200, submission.text)
        approved = await self.client.post(f'/api/planning/plans/{pid}/department-reviews', headers=director,
            json={'submission_id': submission.json()['id'], 'task_id': task_id,
                  'approved': True, 'reason': '教师申报通过'})
        self.assertEqual(approved.status_code, 200, approved.text)
        official = self.db.get(TeachingTask, task_id)
        official_payload = dict(official.payload)
        before_revision = self.db.get(AcademicPlan, pid).revision
        board = await self.client.get(f'/api/planning/plans/{pid}/department-schedule', headers=director)
        self.assertEqual(board.status_code, 200, board.text)
        row = next(item for item in board.json()['tasks'] if item['id'] == task_id)
        proposal = {'base_revision': before_revision, 'base_fingerprint': row['base_fingerprint'],
                    'teacher_ids': [7], 'reason': '教研室调整建议'}
        response = await self.client.put(
            f'/api/planning/plans/{pid}/tasks/{task_id}/department-schedule-draft',
            headers=director, json=proposal)
        self.assertEqual(response.status_code, 200, response.text)
        self.db.expire_all()
        self.assertEqual(self.db.get(TeachingTask, task_id).payload, official_payload)
        self.assertEqual(self.db.query(PeriodSlot).filter_by(task_id=task_id).count(), 0)
        self.assertIsNone(self.db.get(TeachingAssignment, task_id))
        self.assertEqual(self.db.get(AcademicPlan, pid).revision, before_revision)
        board = await self.client.get(f'/api/planning/plans/{pid}/department-schedule', headers=director)
        self.assertEqual(board.status_code, 200, board.text)
        row = next(item for item in board.json()['tasks'] if item['id'] == task_id)
        self.assertEqual(row['proposal']['teacher_ids'], [7])

    async def test_schedule_fields_are_rejected_from_department_proposal(self):
        pid, task_ids, _, _, director, _ = await self.prepare()
        response = await self.client.get(f'/api/planning/plans/{pid}/department-schedule', headers=director)
        row = next(item for item in response.json()['tasks'] if item['id'] == task_ids['Design A'])
        forbidden = await self.client.put(
            f'/api/planning/plans/{pid}/tasks/{task_ids["Design A"]}/department-schedule-draft',
            headers=director, json={'base_revision': row['plan_revision'],
                'base_fingerprint': row['base_fingerprint'], 'teacher_ids': [7], 'room_id': None,
                'start_week': 2, 'end_week': 3, 'slots': [], 'reason': '企图修改系统安排'})
        self.assertEqual(forbidden.status_code, 422, forbidden.text)
        board = await self.client.get(f'/api/planning/plans/{pid}/department-schedule', headers=director)
        row = next(item for item in board.json()['tasks'] if item['id'] == task_ids['Design A'])
        self.assertIsNone(row['proposal_id'])

    async def test_director_proposal_does_not_require_reason(self):
        pid, task_ids, admin, teacher, director, _ = await self.prepare()
        task_id=task_ids['Design A']
        state=(await self.client.get(f'/api/planning/plans/{pid}',headers=teacher)).json()
        design_ids=[tid for group,tid in task_ids.items() if group.startswith('Design')]
        draft=await self.client.put(f'/api/planning/plans/{pid}/draft',headers=teacher,
            json={'revision':0,'plan_revision':state['revision'],'task_ids':design_ids})
        submission=await self.client.post(f'/api/planning/plans/{pid}/submit',headers=teacher,
            json={'revision':draft.json()['revision']})
        for tid in design_ids:
            approved=await self.client.post(f'/api/planning/plans/{pid}/department-reviews',headers=director,
                json={'submission_id':submission.json()['id'],'task_id':tid,'approved':True,'reason':'初审通过'})
            self.assertEqual(approved.status_code,200,approved.text)
        await self.client.post(f'/api/planning/plans/{pid}/match',headers=admin)
        board=(await self.client.get(f'/api/planning/plans/{pid}/department-schedule',headers=director)).json()
        row=next(item for item in board['tasks'] if item['id']==task_id)
        response=await self.client.put(f'/api/planning/plans/{pid}/tasks/{task_id}/department-schedule-draft',
            headers=director,json={'base_revision':row['plan_revision'],'base_fingerprint':row['base_fingerprint'],'teacher_ids':[7]})
        self.assertEqual(response.status_code,200,response.text)

    async def test_teacher_proposal_does_not_require_a_department_application(self):
        pid, task_ids, _, _, director, _ = await self.prepare()
        response = await self.client.get(f'/api/planning/plans/{pid}/department-schedule', headers=director)
        row = next(item for item in response.json()['tasks'] if item['id'] == task_ids['Design A'])
        invalid = await self.client.put(
            f'/api/planning/plans/{pid}/tasks/{task_ids["Design A"]}/department-schedule-draft',
            headers=director, json={'base_revision': row['plan_revision'],
                'base_fingerprint': row['base_fingerprint'], 'teacher_ids': [7],
                'reason': '建议任课教师'})
        self.assertEqual(invalid.status_code, 200, invalid.text)

    async def test_approved_teacher_proposal_changes_only_teacher_assignment(self):
        pid, task_ids, admin, teacher, director, other_director = await self.prepare()
        task_id = task_ids['Design A']
        state = (await self.client.get(f'/api/planning/plans/{pid}', headers=teacher)).json()
        design_task_ids = [task_id for group, task_id in task_ids.items() if group.startswith('Design')]
        draft = await self.client.put(f'/api/planning/plans/{pid}/draft', headers=teacher,
            json={'revision': 0, 'plan_revision': state['revision'], 'task_ids': design_task_ids})
        self.assertEqual(draft.status_code, 200, draft.text)
        submission = await self.client.post(f'/api/planning/plans/{pid}/submit', headers=teacher,
            json={'revision': draft.json()['revision']})
        self.assertEqual(submission.status_code, 200, submission.text)
        for group, task_id_for_group in task_ids.items():
            if not group.startswith('Design'):
                continue
            review_headers = director
            approved = await self.client.post(f'/api/planning/plans/{pid}/department-reviews', headers=review_headers,
                json={'submission_id': submission.json()['id'], 'task_id': task_id_for_group,
                      'approved': True, 'reason': '教师申请初审通过'})
            self.assertEqual(approved.status_code, 200, approved.text)
        matched = await self.client.post(f'/api/planning/plans/{pid}/match', headers=admin)
        self.assertEqual(matched.status_code, 200, matched.text)
        task_before = dict(self.db.get(TeachingTask, task_id).payload)
        slots_before = [(slot.day, slot.start, slot.count, slot.phase) for slot in
                        self.db.query(PeriodSlot).filter_by(task_id=task_id).order_by(PeriodSlot.id)]
        proposal_id = await self.propose(pid, task_id, director, changes={'teacher_ids': [7]})
        submitted = await self.client.post(
            f'/api/planning/plans/{pid}/tasks/{task_id}/department-schedule-submit', headers=director,
            json={'proposal_id': proposal_id})
        self.assertEqual(submitted.status_code, 200, submitted.text)
        confirmed = await self.client.post(
            f'/api/planning/plans/{pid}/tasks/{task_id}/department-schedule-decision', headers=admin,
            json={'proposal_id': proposal_id, 'approved': True, 'reason': '确认教师调整'})
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.db.expire_all()
        assignment = self.db.get(TeachingAssignment, task_id)
        self.assertEqual(assignment.teacher_ids, [7])
        self.assertEqual(self.db.get(TeachingTask, task_id).payload, task_before)
        slots_after = [(slot.day, slot.start, slot.count, slot.phase) for slot in
                       self.db.query(PeriodSlot).filter_by(task_id=task_id).order_by(PeriodSlot.id)]
        self.assertEqual(slots_after, slots_before)

    async def test_other_department_and_teacher_cannot_read_or_change_course_board(self):
        pid, task_ids, admin, teacher, director, other_director = await self.prepare()
        other_board = await self.client.get(f'/api/planning/plans/{pid}/department-schedule', headers=other_director)
        self.assertEqual(other_board.status_code, 200, other_board.text)
        outside = next(row for row in other_board.json()['tasks'] if row['id'] == task_ids['Packaging A'])
        forbidden = await self.client.put(
            f'/api/planning/plans/{pid}/tasks/{task_ids["Design A"]}/department-schedule-draft',
            headers=other_director, json={'base_revision': outside['plan_revision'],
                'base_fingerprint': outside['base_fingerprint'], 'teacher_ids': [7], 'reason': 'outside scope'})
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual((await self.client.get(
            f'/api/planning/plans/{pid}/department-schedule', headers=teacher)).status_code, 403)
        admin_draft = await self.client.put(
            f'/api/planning/plans/{pid}/tasks/{task_ids["Design A"]}/department-schedule-draft',
            headers=admin, json={'base_revision': outside['plan_revision'],
                'base_fingerprint': outside['base_fingerprint'], 'teacher_ids': [7], 'reason': '代主任调剂'})
        self.assertEqual(admin_draft.status_code, 403)


if __name__ == '__main__':
    unittest.main()
