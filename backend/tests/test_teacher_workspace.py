from app.models.class_info import ClassInfo
from app.models.classroom import Classroom
from app.models.course import Course
from app.models.schedule import ScheduleEntry
from app.models.teacher import Teacher
import unittest
import test_debug_mode


class TeacherWorkspaceTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown = test_debug_mode.DebugModeTests.asyncTearDown
    async def teacher_headers(self):
        response = await self.client.post('/api/debug/session', json={'role': 'teacher', 'teacher_id': 7})
        return {'Authorization': f"Bearer {response.json()['access_token']}"}

    async def test_teacher_cannot_access_management_routes(self):
        headers = await self.teacher_headers()
        for path in ['/api/classes/', '/api/teachers/', '/api/courses/', '/api/classrooms/',
                     '/api/constraints/', '/api/schedules/', '/api/schedules/versions',
                     '/api/io/template/classes', '/api/io/report', '/api/io/export/excel']:
            with self.subTest(path=path):
                self.assertEqual((await self.client.get(path, headers=headers)).status_code, 403)
        response = await self.client.post('/api/courses/', headers=headers, json={
            'name': 'Forbidden course', 'course_code': 'FORBIDDEN'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.db.query(Course).count(), 0)
        self.assertEqual((await self.client.get('/api/teachers/')).status_code, 401)
        admin = await self.client.post('/api/debug/session', json={'role': 'admin'})
        response = await self.client.get('/api/teachers/', headers={
            'Authorization': f"Bearer {admin.json()['access_token']}"})
        self.assertEqual(response.status_code, 200)

    async def test_my_timetable_never_exposes_other_teacher_and_defaults_latest(self):
        self.db.add_all([
            Teacher(id=8, name='Other teacher', teacher_code='TEST-8'),
            ClassInfo(id=21, name='Demo class', grade='2026'),
            Classroom(id=31, name='Demo room', room_code='ROOM-31', capacity=40),
            Course(id=11, name='Demo course', course_code='COURSE-11'),
        ])
        self.db.commit()
        for entry_id, teacher_id, version in [(701, 7, 'schedule_100_old'),
                                              (702, 7, 'schedule_200_new'),
                                              (703, 8, 'schedule_200_new'),
                                              (704, 8, 'schedule_150_other')]:
            self.db.add(ScheduleEntry(id=entry_id, schedule_version=version,
                teacher_id=teacher_id, course_id=11, class_id=21, classroom_id=31,
                week_number=1, day_of_week=1, period_start=1, period_end=1))
        self.db.commit()
        headers = await self.teacher_headers()
        response = await self.client.get('/api/my/timetable?teacher_id=8', headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([e['id'] for e in response.json()], [702])
        old = await self.client.get('/api/my/timetable?version=schedule_100_old', headers=headers)
        self.assertEqual([e['id'] for e in old.json()], [701])
        self.assertEqual((await self.client.get('/api/my/timetable')).status_code, 401)
        overview = await self.client.get('/api/my/planning-timetable?teacher_id=8', headers=headers)
        self.assertEqual(overview.status_code, 200, overview.text)
        self.assertEqual(overview.json()['legacy_versions'], ['schedule_200_new', 'schedule_100_old'])
        self.assertEqual(overview.json()['batches'], [])
        other = await self.client.get('/api/my/timetable?version=schedule_150_other', headers=headers)
        self.assertEqual(other.json(), [])
