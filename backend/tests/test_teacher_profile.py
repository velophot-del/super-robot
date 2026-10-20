from datetime import date,datetime
import unittest
import test_debug_mode
from app.models.planning import AcademicPlan,TeacherProfile,PreferenceDraft


class TeacherProfileTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown=test_debug_mode.DebugModeTests.asyncTearDown

    async def headers(self,role='teacher'):
        r=await self.client.post('/api/debug/session',json={'role':role,'teacher_id':7 if role=='teacher' else None})
        return {'Authorization':'Bearer '+r.json()['access_token']}

    async def test_incomplete_profile_blocks_both_draft_and_submission(self):
        h=await self.headers()
        self.db.add(AcademicPlan(id=1,name='Term',start_date=date(2027,2,1),weeks=20,deadline=datetime(2027,1,31),state='open',revision=1));self.db.commit()
        r=await self.client.put('/api/planning/plans/1/draft',headers=h,json={'revision':0,'plan_revision':1,'task_ids':[]})
        self.assertEqual(r.status_code,403,r.text);self.assertIn('个人资料',r.text)
        r=await self.client.post('/api/planning/plans/1/submit',headers=h,json={'revision':1})
        self.assertEqual(r.status_code,403,r.text)
        p=(await self.client.get('/api/planning/self-profile',headers=h)).json()
        self.assertFalse(p['ready']);self.assertIn('擅长课程',p['missing'])

    async def test_self_update_preserves_admin_fields_and_rejects_forgery_and_stale_save(self):
        self.db.add(TeacherProfile(teacher_id=7,revision=3,payload={'direction':'Admin direction','tags':['old'],'verified':True,
            'team_codes':['A'],'taught_codes':['B'],'weekly_limit':12,'course_limit':2,'external_hours':{'1':4}}));self.db.commit()
        h=await self.headers();url='/api/planning/self-profile'
        data={'revision':3,'direction':'Design','tags':[' type ','layout'],'skilled_courses':['Typography'],'introduction':'Studio teaching'}
        forged=await self.client.put(url,headers=h,json={**data,'verified':True,'weekly_limit':40,'teacher_id':8})
        self.assertEqual(forged.status_code,422)
        r=await self.client.put(url,headers=h,json=data)
        self.assertEqual(r.status_code,200,r.text);self.assertTrue(r.json()['ready']);self.assertEqual(r.json()['revision'],4)
        p=self.db.get(TeacherProfile,7);self.assertEqual(p.payload['weekly_limit'],12)
        self.assertTrue(p.payload['verified']);self.assertEqual(p.payload['team_codes'],['A']);self.assertEqual(p.payload['external_hours'],{'1':4})
        self.assertEqual(r.json()['profile']['tags'],['type','layout'])
        self.assertEqual((await self.client.put(url,headers=h,json=data)).status_code,409)
        bad={**data,'revision':4,'direction':'   '}
        self.assertEqual((await self.client.put(url,headers=h,json=bad)).status_code,422)
        admin=await self.headers('admin')
        self.assertEqual((await self.client.get(url,headers=admin)).status_code,403)
        r=await self.client.put('/api/planning/profiles/7',headers=admin,json={'direction':'Managed','tags':['admin'],'verified':True})
        self.assertEqual(r.status_code,200,r.text)
        own=(await self.client.get(url,headers=h)).json()
        self.assertEqual(own['profile']['direction'],'Design')
        self.assertTrue(own['ready'])

    async def test_self_fields_drive_match_without_claiming_admin_credentials(self):
        from app.api.planning import profile_for
        from app.services.teacher_course_matching import score_candidate
        h=await self.headers()
        r=await self.client.put('/api/planning/self-profile',headers=h,json={'revision':0,'direction':'Design','tags':['type'],'skilled_courses':['Typography']})
        self.assertEqual(r.status_code,200,r.text)
        profile=profile_for(self.db,7)
        task={'id':1,'name':'Typography','code':'A','group':'G','required_hours':4,'start_week':1,'end_week':1,
            'direction':'Design','tags':['type'],'profile_verified':True,'slots':[{'day':1,'start':1,'count':4}]}
        result=score_candidate(self.db,AcademicPlan(id=1,start_date=date(2027,2,1),weeks=20),task,7,profile,0,[])
        self.assertEqual(result['professional_fit'],100);self.assertTrue(result['skilled_course_match'])
        self.assertEqual(result['professional_profile_source'],'self_declared')
        self.assertEqual(result['components'][0]['score'],0);self.assertEqual(result['components'][3]['score'],0)
