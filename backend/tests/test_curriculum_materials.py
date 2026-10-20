from io import BytesIO
import unittest
import test_debug_mode
from openpyxl import Workbook


class CurriculumMaterialsTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown = test_debug_mode.DebugModeTests.asyncTearDown

    async def test_upload_preview_activate_and_generate_idempotently(self):
        token=(await self.client.post('/api/debug/session',json={'role':'admin'})).json()['access_token']
        h={'Authorization':'Bearer '+token}
        wb=Workbook();ws=wb.active
        ws.append(['课程编码','课程名称','学分','总学时','开课学期','专业方向','领域标签'])
        ws.append(['DES101','Typography',1.5,32,2,'Design','type,layout'])
        data=BytesIO();wb.save(data)
        r=await self.client.post('/api/planning/curricula/import',headers=h,
            data={'major':'Design','cohort':'2026','revision':'1'},
            files={'file':('scheme.xlsx',data.getvalue(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['rows'][0]['credits'],1.5)
        doc=r.json()['id']
        self.assertEqual((await self.client.post(f'/api/planning/curricula/{doc}/activate',headers=h)).status_code,200)
        r=await self.client.post('/api/planning/plans',headers=h,json={
            'name':'Term','start_date':'2027-02-01','weeks':20,'deadline':'2027-01-31T23:59:59',
            'major':'Design','cohort':'2026','semester':2,'groups':['A','B','C','D']})
        pid=r.json()['id']
        for _ in range(2):
            r=await self.client.post(f'/api/planning/plans/{pid}/generate',headers=h)
            self.assertEqual(r.status_code,200,r.text)
            self.assertEqual(r.json()['task_count'],4)
        state=(await self.client.get(f'/api/planning/plans/{pid}',headers=h)).json()
        self.assertEqual(len(state['tasks']),4)
        self.assertEqual(state['tasks'][0]['credits'],1.5)
        self.assertEqual((await self.client.post(f'/api/planning/plans/{pid}/open',headers=h)).status_code,409)
