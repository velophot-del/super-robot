"""教师详情路由与班级/教师课程分配的最新版本隔离。"""
import unittest
import test_debug_mode
from app.models.class_info import ClassInfo
from app.models.classroom import Classroom
from app.models.course import Course
from app.models.schedule import ScheduleEntry


class TeacherCourseViewTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown = test_debug_mode.DebugModeTests.asyncTearDown

    async def admin_headers(self):
        session = await self.client.post('/api/debug/session', json={'role': 'admin'})
        return {'Authorization': f"Bearer {session.json()['access_token']}"}

    async def test_teacher_detail_route_is_registered(self):
        headers = await self.admin_headers()
        response = await self.client.get('/api/teachers/7', headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['id'], 7)
        self.assertEqual(response.json()['teacher_code'], 'TEST-7')
        missing = await self.client.get('/api/teachers/999', headers=headers)
        self.assertEqual(missing.status_code, 404)

    async def test_course_views_only_count_latest_schedule_version(self):
        self.db.add_all([
            Course(id=1, name='Design', course_code='C1', semester=2),
            ClassInfo(id=1, name='Class A', grade='2026', department='Design'),
            Classroom(id=1, name='Room 1', room_code='R01', capacity=40),
        ])
        self.db.flush()
        for version, days in [('schedule_100_aaaaaaaa', 2), ('schedule_200_bbbbbbbb', 1)]:
            for day in range(1, days + 1):
                self.db.add(ScheduleEntry(
                    schedule_version=version, course_id=1, teacher_id=7, class_id=1,
                    classroom_id=1, week_number=1, day_of_week=day,
                    period_start=1, period_end=2, status='confirmed', is_manual=0))
        self.db.commit()
        headers = await self.admin_headers()

        class_view = (await self.client.get('/api/classes/1/courses', headers=headers)).json()
        self.assertEqual([row['time_slots'] for row in class_view['courses']], [1])
        teacher_view = (await self.client.get('/api/teachers/7/courses', headers=headers)).json()
        self.assertEqual([row['time_slots'] for row in teacher_view['courses']], [1])

        old_view = (await self.client.get('/api/classes/1/courses',
                                          params={'version': 'schedule_100_aaaaaaaa'},
                                          headers=headers)).json()
        self.assertEqual([row['time_slots'] for row in old_view['courses']], [2])
