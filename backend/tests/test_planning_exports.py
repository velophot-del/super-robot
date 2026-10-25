from datetime import datetime
from io import BytesIO
from zipfile import ZipFile
import test_debug_mode
import unittest
from app.models.planning import AcademicPlan,PublishedPlan,TeachingTask
from datetime import date


class PlanningExportsTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown=test_debug_mode.DebugModeTests.asyncTearDown

    async def test_blank_word_template_does_not_require_a_saved_cycle(self):
        session=await self.client.post('/api/debug/session',json={'role':'admin'})
        headers={'Authorization':'Bearer '+session.json()['access_token']}
        response=await self.client.get('/api/planning/exports/word',headers=headers,params={
            'blank':True,'major':'Design','cohort':'2026','start_date':'2027-02-01','weeks':20})
        self.assertEqual(response.status_code,200,response.text)
        with ZipFile(BytesIO(response.content)) as archive:
            text=archive.read('word/document.xml').decode()
        self.assertIn('Design',text)
        self.assertIn('2026',text)
        self.assertIn('暂无课程任务（空白稿）',text)
        self.assertEqual(self.db.query(AcademicPlan).count(),0)

    async def test_major_export_aggregates_cohorts_for_all_signed_in_users(self):
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
        for h in [admin,teacher]:
            r=await self.client.get(url,headers=h)
            self.assertEqual(r.status_code,200,r.text)
            with ZipFile(BytesIO(r.content)) as z:text=z.read('word/document.xml').decode()
            self.assertIn('Course-1',text);self.assertIn('Course-2',text);self.assertNotIn('Course-3',text)
        r=await self.client.get(url+'&cohort=2025',headers=admin)
        with ZipFile(BytesIO(r.content)) as z:self.assertNotIn('Course-2',z.read('word/document.xml').decode())
        self.assertEqual((await self.client.get(url.replace('Design','Missing'),headers=admin)).status_code,404)
        self.assertEqual((await self.client.get(url)).status_code,401)

    async def test_draft_and_blank_plans_export_without_publication(self):
        self.db.add_all([
            AcademicPlan(id=10,name='Process',start_date=date(2027,2,1),weeks=20,
                         deadline=datetime(2027,1,1),state='draft',settings={'term':2}),
            AcademicPlan(id=11,name='Blank',start_date=date(2027,3,1),weeks=20,
                         deadline=datetime(2027,1,1),state='draft',settings={'term':2}),
        ])
        self.db.add(TeachingTask(plan_id=10,payload={
            'name':'Draft Course','code':'D1','group':'G','major':'Design','cohort':'2026',
            'start_week':1,'end_week':2,'credits':2,'required_hours':8,'teacher_count':1,
        }))
        self.db.commit()
        async def auth(role):
            r=await self.client.post('/api/debug/session',json={'role':role,'teacher_id':7 if role=='teacher' else None})
            return {'Authorization':'Bearer '+r.json()['access_token']}
        admin=await auth('admin');teacher=await auth('teacher')
        options=(await self.client.get('/api/planning/exports/options',headers=admin)).json()
        self.assertEqual({row['plan_id'] for row in options},{10,11})
        self.assertIn('',{row['major'] for row in options if row['plan_id']==11})
        process=await self.client.get(
            '/api/planning/exports/word?plan_id=10&major=Design&start_date=2027-02-01&weeks=20',
            headers=teacher)
        self.assertEqual(process.status_code,200,process.text)
        with ZipFile(BytesIO(process.content)) as z:
            self.assertIn('Draft Course',z.read('word/document.xml').decode())
        blank=await self.client.get(
            '/api/planning/exports/word?plan_id=11&start_date=2027-03-01&weeks=20',
            headers=admin)
        self.assertEqual(blank.status_code,200,blank.text)
        with ZipFile(BytesIO(blank.content)) as z:
            text=z.read('word/document.xml').decode()
        self.assertIn('暂无课程任务（空白稿）',text)
        self.assertIn('未设置专业',text)
