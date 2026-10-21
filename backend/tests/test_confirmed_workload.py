import unittest
from datetime import date, datetime
import test_debug_mode
from app.models.teacher import Teacher
from app.models.planning import (AcademicPlan, TeachingTask, PeriodSlot, TeachingAssignment,
                                 MatchRun, TeacherWorkloadEstimate, TeacherProfile)


class ConfirmedWorkloadTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown = test_debug_mode.DebugModeTests.asyncTearDown

    async def test_workload_uses_class_base_real_weeks_tail_hours_and_confirmed_assignments(self):
        self.db.add(Teacher(id=8, name='Other teacher', teacher_code='T8'))
        self.db.add(TeacherProfile(teacher_id=7, revision=1, payload={'self_profile': {
            'direction': 'Design', 'tags': ['type'], 'skilled_courses': ['Typography'],
            'participating_course_ids': []}}))
        self.db.add(AcademicPlan(id=1, name='Term', start_date=date(2026, 9, 7), weeks=20,
                                 deadline=datetime(2026, 8, 31), state='matched',
                                 settings={'groups': ['G']}))
        self.db.add(MatchRun(id=1, plan_id=1, payload={}))
        self.db.add_all([
            TeachingTask(id=1, plan_id=1, payload={'name': '普通课程', 'group': 'G', 'required_hours': 8,
                                                   'student_count': 30, 'start_week': 1, 'end_week': 2}),
            TeachingTask(id=2, plan_id=1, payload={'name': '尾周课程', 'group': 'G', 'required_hours': 10,
                                                   'student_count': 25, 'start_week': 1, 'end_week': 3,
                                                   'tail_weeks': 1}),
            TeachingTask(id=3, plan_id=1, payload={'name': '多人课程', 'group': 'G', 'required_hours': 8,
                                                   'student_count': 25, 'start_week': 1, 'end_week': 2,
                                                   'teacher_count': 2}),
            TeachingTask(id=4, plan_id=1, payload={'name': '毕业设计', 'group': 'G', 'required_hours': 144,
                                                   'student_count': 30, 'start_week': 1, 'end_week': 16}),
            TeachingTask(id=5, plan_id=1, payload={'name': '毕业论文', 'group': 'G', 'required_hours': 72,
                                                   'student_count': 30, 'start_week': 1, 'end_week': 16}),
            TeachingTask(id=6, plan_id=1, payload={'name': '未确认课程', 'group': 'G', 'required_hours': 8,
                                                   'student_count': 30, 'start_week': 1, 'end_week': 2}),
            TeachingTask(id=7, plan_id=1, payload={'name': '无节次尾周课程', 'group': 'G', 'required_hours': 10,
                                                   'student_count': 25, 'start_week': 1, 'end_week': 3,
                                                   'tail_weeks': 1, 'source': {'course_metadata': {
                                                       'weekly_hours': 4, 'tail_hours': 2, 'teaching_weeks': 3}}}),
            TeachingTask(id=8, plan_id=1, payload={'name': '待选课人数课程', 'group': 'G', 'required_hours': 8,
                                                   'student_count': 0, 'start_week': 1, 'end_week': 2}),
        ])
        self.db.add_all([
            PeriodSlot(task_id=1, day=1, start=1, count=4, phase='normal'),
            PeriodSlot(task_id=2, day=1, start=1, count=4, phase='normal'),
            PeriodSlot(task_id=2, day=2, start=1, count=2, phase='tail'),
            PeriodSlot(task_id=3, day=1, start=1, count=4, phase='normal'),
            TeachingAssignment(task_id=1, teacher_ids=[7], match_id=1, locked=True),
            TeachingAssignment(task_id=2, teacher_ids=[7], match_id=1, locked=True),
            TeachingAssignment(task_id=3, teacher_ids=[7, 8], match_id=1, locked=True),
            TeachingAssignment(task_id=4, teacher_ids=[7], match_id=1, locked=True),
            TeachingAssignment(task_id=5, teacher_ids=[7], match_id=1, locked=True),
            TeachingAssignment(task_id=7, teacher_ids=[7], match_id=1, locked=True),
            TeachingAssignment(task_id=8, teacher_ids=[7], match_id=1, locked=True),
        ])
        self.db.add_all([
            TeacherWorkloadEstimate(plan_id=1, teacher_id=7, task_id=3, revision=1, payload={'weeks': 3}),
            TeacherWorkloadEstimate(plan_id=1, teacher_id=8, task_id=3, revision=1, payload={'weeks': 1}),
            TeacherWorkloadEstimate(plan_id=1, teacher_id=7, task_id=4, revision=1, payload={'guidance_students': 2}),
            TeacherWorkloadEstimate(plan_id=1, teacher_id=7, task_id=5, revision=1, payload={'guidance_students': 3}),
        ])
        self.db.commit()
        token = (await self.client.post('/api/debug/session', json={'role': 'teacher', 'teacher_id': 7})).json()['access_token']
        headers = {'Authorization': 'Bearer ' + token}
        result = await self.client.get('/api/planning/plans/1/my-workload', headers=headers)
        self.assertEqual(result.status_code, 200, result.text)
        data = result.json()
        by_id = {row['task_id']: row for row in data['rows']}
        self.assertNotIn(6, by_id)
        self.assertEqual(by_id[1]['workload'], 8.8)      # 8 课时 × 30 人基数 1.1
        self.assertEqual(by_id[2]['workload'], 10)       # 尾周仅 2 课时，按 4+4+2 实际计算
        self.assertEqual(by_id[3]['workload'], 6)        # 8 课时按 3:1 周分配
        self.assertEqual(by_id[4]['workload'], 24)       # 2 生 × 12
        self.assertEqual(by_id[5]['workload'], 24)       # 3 生 × 8
        self.assertEqual(by_id[7]['workload'], 10)       # 无节次：2 个普通周×4 + 1 个尾周×2
        self.assertEqual(by_id[3]['allocation'], '3/4')
        self.assertEqual(data['total'], 82.8)
        self.assertEqual(data['pending'], 1)            # 任务8实际选课人数尚未回填
        self.assertIn('待学生选课结束后统计实际授课人数', by_id[8]['note'])

        # 缺少另一位授课教师的周数时，本项无法准确分配，应标记待补充。
        self.db.query(TeacherWorkloadEstimate).filter_by(plan_id=1, teacher_id=8, task_id=3).delete()
        self.db.commit()
        pending = (await self.client.get('/api/planning/plans/1/my-workload', headers=headers)).json()
        self.assertEqual(pending['pending'], 2)
        self.assertEqual({row['task_id'] for row in pending['rows'] if row['status'] == 'pending'}, {3, 8})
        self.assertEqual(pending['total'], 76.8)

        # 审核确认后仍可补充本人指导人数，发布后才冻结。
        updated = await self.client.put('/api/planning/plans/1/tasks/4/workload-estimate', headers=headers,
                                        json={'revision': 1, 'guidance_students': 3})
        self.assertEqual(updated.status_code, 200, updated.text)
        refreshed = (await self.client.get('/api/planning/plans/1/my-workload', headers=headers)).json()
        self.assertEqual({row['task_id']: row['workload'] for row in refreshed['rows']}[4], 36)
