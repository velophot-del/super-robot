from io import BytesIO
import unittest
from openpyxl import Workbook
import test_debug_mode
from app.models.course import Course


class CourseXlsxImportTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown=test_debug_mode.DebugModeTests.asyncTearDown

    async def test_preview_is_read_only_and_confirmation_imports_only_valid_new_rows_once(self):
        wb=Workbook();one=wb.active;one.title='课程表A'
        one.append(['课程名称','课程编码','上课学期','总课时','课程类型','课程性质'])
        one.append(['构成设计','A101',1,32,'专业课','必修课'])
        one.append(['错误学期','BAD',13,32,'专业课','必修课'])
        two=wb.create_sheet('课程表B');two.append(['课程名称','课程编码','上课学期','总课时'])
        two.append(['重复课程','A101',2,32])
        out=BytesIO();wb.save(out)
        headers={'Authorization':'Bearer '+(await self.client.post('/api/debug/session',json={'role':'admin'})).json()['access_token']}
        preview=await self.client.post('/api/io/xlsx/courses/preview',headers=headers,
            files={'file':('courses.xlsx',out.getvalue())})
        self.assertEqual(preview.status_code,200,preview.text)
        body=preview.json()
        self.assertEqual(self.db.query(Course).count(),0)
        self.assertEqual(body['counts'],{'new':1,'duplicate':1,'invalid':1})
        self.assertIn('课程表B',body['rows'][2]['source_sheet'])
        confirmed=await self.client.post('/api/io/xlsx/courses/confirm',headers=headers,
            json={'preview_id':body['preview_id'],'token':body['token']})
        self.assertEqual(confirmed.status_code,200,confirmed.text)
        self.assertEqual(confirmed.json()['imported'],1)
        self.assertEqual(self.db.query(Course).count(),1)
        replay=await self.client.post('/api/io/xlsx/courses/confirm',headers=headers,
            json={'preview_id':body['preview_id'],'token':body['token']})
        self.assertEqual(replay.status_code,409)


if __name__=='__main__':
    unittest.main()
