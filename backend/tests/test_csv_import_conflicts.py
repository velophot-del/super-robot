"""CSV跳过重复记录并继续导入新数据，不覆盖原记录。"""
import unittest
import test_debug_mode
from app.models.classroom import Classroom


class CsvImportConflictTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown = test_debug_mode.DebugModeTests.asyncTearDown

    async def upload(self, rows):
        session = await self.client.post('/api/debug/session', json={'role': 'admin'})
        return await self.client.post('/api/io/csv/classrooms',
            headers={'Authorization': f"Bearer {session.json()['access_token']}"},
            files={'file': ('rooms.csv', ('教室名称,教室编号,容量\n'+rows).encode('utf-8'), 'text/csv')})

    async def test_existing_rows_skipped_and_new_rows_imported(self):
        self.db.add(Classroom(name='Existing', room_code='R1', capacity=30))
        self.db.commit()
        response = await self.upload('Existing,R1,99\nNew,R2,40\nOther,R1,50\nExisting,R3,50\n')
        result = response.json()
        self.assertTrue(result['success'], response.text)
        self.assertEqual((result['imported'], result['skipped']), (1, 3))
        self.assertIn('教室编号', ' '.join(result['warnings']))
        self.assertIn('第4行', ' '.join(result['warnings']))
        self.assertEqual(self.db.query(Classroom).count(), 2)
        self.assertEqual(self.db.query(Classroom).filter_by(room_code='R1').one().capacity, 30)

    async def test_duplicate_within_file_keeps_first_record(self):
        response = await self.upload('First,R1,30\nSecond,R1,40\nFirst,R2,50\nThird,R3,60\n')
        result = response.json()
        self.assertTrue(result['success'], response.text)
        self.assertEqual((result['imported'], result['skipped']), (2, 2))
        self.assertIn('第3行', ' '.join(result['warnings']))
        self.assertEqual(self.db.query(Classroom).count(), 2)
        self.assertEqual(self.db.query(Classroom).filter_by(room_code='R1').one().capacity, 30)

    async def test_skipped_row_does_not_reserve_unwritten_values(self):
        self.db.add(Classroom(name='Existing', room_code='R1', capacity=30))
        self.db.commit()
        result = (await self.upload('New,R1,40\nNew,R2,50\n')).json()
        self.assertTrue(result['success'])
        self.assertEqual((result['imported'], result['skipped']), (1, 1))
        self.assertEqual(self.db.query(Classroom).filter_by(room_code='R2').one().name, 'New')

    async def test_valid_import_then_repeat_is_successful_noop(self):
        rows = 'First,R1,30\nSecond,R2,40\n'
        response = await self.upload(rows)
        self.assertTrue(response.json()['success'], response.text)
        self.assertEqual(response.json()['imported'], 2)
        repeated = await self.upload(rows)
        result = repeated.json()
        self.assertTrue(result['success'], repeated.text)
        self.assertEqual((result['imported'], result['skipped']), (0, 2))
        self.assertIn('跳过2条', result['summary'])
        self.assertEqual(self.db.query(Classroom).count(), 2)
