from io import BytesIO
import unittest
from openpyxl import Workbook
import test_debug_mode


class CourseLibrarySyncTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown=test_debug_mode.DebugModeTests.asyncTearDown

    async def test_activation_syncs_library_fractional_credits_and_is_idempotent(self):
        t=(await self.client.post('/api/debug/session',json={'role':'admin'})).json()['access_token'];h={'Authorization':'Bearer '+t}
        wb=Workbook();ws=wb.active;ws.append(['课程编码','课程名称','学分','总学时','开课学期','上课周数','周课时']);ws.append(['A','Design',0.5,8,1,1,8]);out=BytesIO();wb.save(out)
        r=await self.client.post('/api/planning/curricula/import',headers=h,data={'major':'Design','cohort':'2026','revision':1},files={'file':('scheme.xlsx',out.getvalue())});self.assertEqual(r.status_code,200,r.text);did=r.json()['id']
        for _ in range(2):
            r=await self.client.post(f'/api/planning/curricula/{did}/activate',headers=h);self.assertEqual(r.status_code,200,r.text)
        r=await self.client.get('/api/courses/',headers=h);self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(len(r.json()),1);self.assertEqual(r.json()[0]['credits'],0.5)
        self.assertEqual(r.json()[0]['curriculum_sources'][0]['metadata']['teaching_weeks'],1)

    async def test_conflicting_existing_course_is_not_overwritten(self):
        from app.models.course import Course
        from app.models.planning import CurriculumDocument,ActiveCurriculum
        self.db.add(Course(name='Existing',course_code='A',credits=2,total_hours=32));self.db.add(CurriculumDocument(id=1,name='scheme',major='Design',cohort='2026',revision=1,original=b'1',sha256='h',rows=[{'name':'Changed','code':'A','credits':4,'required_hours':72}]))
        self.db.commit()
        h={'Authorization':'Bearer '+(await self.client.post('/api/debug/session',json={'role':'admin'})).json()['access_token']}
        r=await self.client.post('/api/planning/curricula/1/activate',headers=h)
        self.assertEqual(r.status_code,409,r.text)
        self.assertEqual(self.db.query(Course).one().name,'Existing')
        self.assertEqual(self.db.query(ActiveCurriculum).count(),0)
