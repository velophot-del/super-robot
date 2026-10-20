from datetime import datetime
from io import BytesIO
from zipfile import ZipFile
import test_debug_mode
import unittest
from app.models.planning import AcademicPlan,PublishedPlan
from datetime import date


class PlanningExportsTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown=test_debug_mode.DebugModeTests.asyncTearDown

    async def test_major_export_aggregates_cohorts_and_limits_teacher_scope(self):
        for pid,major,cohort,teacher in [(1,'Design','2025',7),(2,'Design','2026',8),(3,'Other','2026',7)]:
            plan={'id':pid,'name':'Term','major':major,'cohort':cohort,'semester':2,'start_date':'2027-02-01','weeks':20}
            task={'id':pid,'name':f'Course-{pid}','group':cohort,'code':str(pid),'start_week':1,'end_week':4,
                'slots':[],'teacher_ids':[teacher],'teacher_names':['Snapshot Teacher'],'credits':2,'required_hours':16}
            self.db.add(AcademicPlan(id=pid,name='Term',start_date=date(2027,2,1),weeks=20,deadline=datetime(2027,1,1),state='published'))
            self.db.add(PublishedPlan(plan_id=pid,payload={'plan':plan,'tasks':[task]}))
        self.db.commit()
        async def auth(role):
            r=await self.client.post('/api/debug/session',json={'role':role,'teacher_id':7 if role=='teacher' else None})
            return {'Authorization':'Bearer '+r.json()['access_token']}
        admin=await auth('admin');teacher=await auth('teacher')
        r=await self.client.get('/api/planning/exports/options',headers=admin)
        self.assertEqual(r.status_code,200,r.text);self.assertEqual(len(r.json()),3)
        url='/api/planning/exports/word?major=Design&start_date=2027-02-01&weeks=20'
        for h,has_other in [(admin,True),(teacher,False)]:
            r=await self.client.get(url,headers=h)
            self.assertEqual(r.status_code,200,r.text)
            with ZipFile(BytesIO(r.content)) as z:text=z.read('word/document.xml').decode()
            self.assertIn('Course-1',text);self.assertEqual('Course-2' in text,has_other);self.assertNotIn('Course-3',text)
        r=await self.client.get(url+'&cohort=2025',headers=admin)
        with ZipFile(BytesIO(r.content)) as z:self.assertNotIn('Course-2',z.read('word/document.xml').decode())
        self.assertEqual((await self.client.get(url.replace('Design','Missing'),headers=admin)).status_code,404)
        self.assertEqual((await self.client.get(url)).status_code,401)
