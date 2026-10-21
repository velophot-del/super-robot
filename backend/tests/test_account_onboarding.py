import unittest
import test_debug_mode
from app.models.user import User
from app.services.auth import hash_password


class AccountOnboardingTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown=test_debug_mode.DebugModeTests.asyncTearDown

    async def admin_headers(self):
        session=await self.client.post('/api/debug/session',json={'role':'admin'})
        return {'Authorization':'Bearer '+session.json()['access_token']}

    async def import_teacher(self,code='001234',name='New teacher'):
        return await self.client.post('/api/io/csv/teachers',headers=await self.admin_headers(),
            files={'file':('teachers.csv',f'姓名,工号\n{name},{code}\n'.encode(),'text/csv')})

    async def test_public_registration_is_disabled(self):
        response=await self.client.post('/api/auth/register',json={'username':'outsider','email':'x@test.com','password':'123456'})
        self.assertEqual(response.status_code,403)
        self.assertEqual(self.db.query(User).count(),0)

    async def test_import_login_password_profile_gate_and_repeat(self):
        response=await self.import_teacher();self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['accounts_created'],1)
        login=await self.client.post('/api/auth/login',json={'username':'001234','password':'123456'})
        self.assertEqual(login.status_code,200,login.text)
        user=login.json()['user'];self.assertTrue(user['password_change_required']);self.assertTrue(user['profile_required'])
        self.assertEqual([(g['capability'],g['scope']) for g in user['grants']],[('teaching','self')])
        headers={'Authorization':'Bearer '+login.json()['access_token']}
        self.assertEqual((await self.client.get('/api/planning/plans',headers=headers)).status_code,403)
        self.assertEqual((await self.client.get('/api/my/timetable',headers=headers)).status_code,403)
        self.assertEqual((await self.client.get('/api/planning/self-profile',headers=headers)).status_code,200)
        for payload in [{'current_password':'wrong','new_password':'NewPassword123'}, {'current_password':'123456','new_password':'123456'}]:
            self.assertNotEqual((await self.client.post('/api/auth/password',headers=headers,json=payload)).status_code,200)
        changed=await self.client.post('/api/auth/password',headers=headers,json={'current_password':'123456','new_password':'NewPassword123'})
        self.assertEqual(changed.status_code,200,changed.text)
        new_headers={'Authorization':'Bearer '+changed.json()['access_token']}
        self.assertEqual((await self.client.get('/api/auth/me',headers=headers)).status_code,401)
        self.assertEqual((await self.client.get('/api/planning/plans',headers=new_headers)).status_code,403)
        profile=(await self.client.get('/api/planning/self-profile',headers=new_headers)).json()
        saved=await self.client.put('/api/planning/self-profile',headers=new_headers,json={'revision':profile['revision'],'direction':'Design','tags':['type'],'skilled_courses':['Typography']})
        self.assertEqual(saved.status_code,200,saved.text)
        self.assertEqual((await self.client.get('/api/planning/plans',headers=new_headers)).status_code,200)
        me=(await self.client.get('/api/auth/me',headers=new_headers)).json()
        self.assertFalse(me['password_change_required']);self.assertFalse(me['profile_required'])
        self.assertEqual((await self.client.get('/api/teachers/',headers=new_headers)).status_code,403)
        repeat=await self.import_teacher();self.assertEqual(repeat.json()['accounts_created'],0)
        self.assertEqual(self.db.query(User).count(),1)
        self.assertEqual((await self.client.post('/api/auth/login',json={'username':'001234','password':'NewPassword123'})).status_code,200)
        self.assertEqual((await self.client.post('/api/auth/login',json={'username':'001234','password':'123456'})).status_code,401)

    async def test_username_conflict_does_not_claim_existing_account(self):
        self.db.add(User(username='001234',email='old@test.com',password_hash=hash_password('ExistingPassword')))
        self.db.commit()
        response=await self.import_teacher()
        self.assertEqual(response.status_code,409,response.text)
        from app.models.planning import TeacherBinding
        from app.models.teacher import Teacher
        self.assertEqual(self.db.query(TeacherBinding).count(),0)
        self.assertEqual(self.db.query(Teacher).count(),1)

    async def test_existing_teacher_gets_account_without_overwriting_roster(self):
        response=await self.import_teacher('TEST-7','Demo teacher')
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['imported'],0)
        self.assertEqual(response.json()['accounts_created'],1)
        from app.models.teacher import Teacher
        self.assertEqual(self.db.query(Teacher).count(),1)
        self.assertEqual((await self.client.post('/api/auth/login',json={'username':'TEST-7','password':'123456'})).status_code,200)

    async def test_profile_completion_alone_does_not_unlock_business(self):
        await self.import_teacher()
        login=await self.client.post('/api/auth/login',json={'username':'001234','password':'123456'})
        headers={'Authorization':'Bearer '+login.json()['access_token']}
        response=await self.client.put('/api/planning/self-profile',headers=headers,json={
            'revision':0,'direction':'Design','tags':['type'],'skilled_courses':['Typography']})
        self.assertEqual(response.status_code,200,response.text)
        me=(await self.client.get('/api/auth/me',headers=headers)).json()
        self.assertTrue(me['password_change_required']);self.assertFalse(me['profile_required'])
        self.assertEqual((await self.client.get('/api/planning/plans',headers=headers)).status_code,403)
