"""从年级页签导入班级时，忽略文件中的年级并统一归属当前年级。"""
import unittest
import test_debug_mode
from app.models.class_info import ClassInfo


class ClassImportCohortTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown = test_debug_mode.DebugModeTests.asyncTearDown

    async def admin_headers(self):
        token = (await self.client.post('/api/debug/session', json={'role': 'admin'})).json()['access_token']
        return {'Authorization': f'Bearer {token}'}

    async def test_csv_class_import_forces_active_grade(self):
        headers = await self.admin_headers()
        csv = '班级名称,年级,学生人数\n视觉2601,2024,30\n'
        response = await self.client.post('/api/io/csv/classes', headers=headers, data={'cohort': '2026'},
            files={'file': ('classes.csv', csv.encode('utf-8'), 'text/csv')})
        self.assertTrue(response.json()['success'], response.text)
        self.assertEqual(self.db.query(ClassInfo).filter_by(name='视觉2601').one().grade, '2026')

    async def test_csv_class_import_without_grade_column_uses_active_grade(self):
        headers = await self.admin_headers()
        csv = '班级名称,学生人数\n包装2601,30\n'
        response = await self.client.post('/api/io/csv/classes', headers=headers, data={'cohort': '2026'},
            files={'file': ('classes.csv', csv.encode('utf-8'), 'text/csv')})
        self.assertTrue(response.json()['success'], response.text)
        self.assertEqual(self.db.query(ClassInfo).filter_by(name='包装2601').one().grade, '2026')

    async def test_class_import_without_cohort_keeps_file_grade(self):
        headers = await self.admin_headers()
        csv = '班级名称,年级\n智交2601,2024\n'
        response = await self.client.post('/api/io/csv/classes', headers=headers,
            files={'file': ('classes.csv', csv.encode('utf-8'), 'text/csv')})
        self.assertTrue(response.json()['success'], response.text)
        self.assertEqual(self.db.query(ClassInfo).filter_by(name='智交2601').one().grade, '2024')
