"""从年级页签导入课程时，忽略文件中的适用年级并统一归属当前年级。"""
import unittest
from io import BytesIO
from openpyxl import Workbook
import test_debug_mode
from app.models.course import Course
from app.schemas.course import CourseResponse


class CourseImportCohortTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown = test_debug_mode.DebugModeTests.asyncTearDown

    async def admin_headers(self):
        token = (await self.client.post('/api/debug/session', json={'role': 'admin'})).json()['access_token']
        return {'Authorization': f'Bearer {token}'}

    async def test_csv_course_import_forces_active_cohort(self):
        headers = await self.admin_headers()
        csv = '课程名称,课程编码,上课学期,总课时,适用年级\n构成设计,C1,1,32,2024\n'
        response = await self.client.post('/api/io/csv/courses', headers=headers, data={'cohort': '2026'},
            files={'file': ('courses.csv', csv.encode('utf-8'), 'text/csv')})
        self.assertTrue(response.json()['success'], response.text)
        self.assertEqual(self.db.query(Course).filter_by(course_code='C1').one().cohort, '2026')

    async def test_xlsx_preview_and_confirm_force_active_cohort(self):
        headers = await self.admin_headers()
        wb = Workbook(); ws = wb.active
        ws.append(['课程名称', '课程编码', '上课学期', '总课时', '适用年级'])
        ws.append(['构成设计', 'X1', 1, 32, '2024'])
        out = BytesIO(); wb.save(out)
        preview = await self.client.post('/api/io/xlsx/courses/preview', headers=headers,
            data={'cohort': '2026'}, files={'file': ('courses.xlsx', out.getvalue())})
        self.assertEqual(preview.status_code, 200, preview.text)
        body = preview.json()
        self.assertEqual(body['target_cohort'], '2026')
        self.assertEqual(body['rows'][0]['data']['cohort'], '2026')
        self.assertEqual(self.db.query(Course).count(), 0)
        confirmed = await self.client.post('/api/io/xlsx/courses/confirm', headers=headers,
            json={'preview_id': body['preview_id'], 'token': body['token']})
        self.assertTrue(confirmed.json()['success'], confirmed.text)
        self.assertEqual(self.db.query(Course).filter_by(course_code='X1').one().cohort, '2026')

    async def test_import_without_cohort_keeps_file_value(self):
        headers = await self.admin_headers()
        csv = '课程名称,课程编码,上课学期,总课时,适用年级\n构成设计,C2,1,32,2024\n'
        response = await self.client.post('/api/io/csv/courses', headers=headers,
            files={'file': ('courses.csv', csv.encode('utf-8'), 'text/csv')})
        self.assertTrue(response.json()['success'], response.text)
        self.assertEqual(self.db.query(Course).filter_by(course_code='C2').one().cohort, '2024')

    async def test_csv_import_converts_legacy_course_schedule_columns(self):
        headers = await self.admin_headers()
        csv = '课程名称,课程编码,上课学期,学期教学次数,每周上课次数,每次课时\n版式设计,C2025,2,18,1,3\n'
        response = await self.client.post('/api/io/csv/courses', headers=headers, data={'cohort': '2025'},
            files={'file': ('2025_courses.csv', csv.encode('utf-8'), 'text/csv')})
        self.assertTrue(response.json()['success'], response.text)
        course = self.db.query(Course).filter_by(course_code='C2025').one()
        self.assertEqual(course.cohort, '2025')
        self.assertEqual(course.total_hours, 54)
        self.assertEqual(course.teaching_weeks, 18)

    async def test_course_response_normalizes_legacy_null_weekdays(self):
        course = Course(name='Legacy course', course_code='LEGACY', semester=1, total_hours=32)
        self.db.add(course); self.db.commit(); self.db.refresh(course)
        course.weekdays = None
        response = CourseResponse.model_validate(course)
        self.assertEqual(response.weekdays, [])
