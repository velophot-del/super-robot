import unittest
import test_debug_mode
from app.models.teacher import Teacher
from app.services.teacher_positions import position_grants
from app.services.authorization import can
from types import SimpleNamespace


class TeacherPositionTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown = test_debug_mode.DebugModeTests.asyncTearDown

    async def test_admin_appointments_and_revocation(self):
        login = await self.client.post('/api/debug/session', json={'role': 'admin'})
        headers = {'Authorization': 'Bearer ' + login.json()['access_token']}
        for position in ['教研室主任', '教研室副主任']:
            saved = await self.client.put('/api/teachers/7', headers=headers,
                json={'position': position, 'review_major': '视觉传达设计'})
            self.assertEqual(saved.status_code, 200, saved.text)
            login = await self.client.post('/api/debug/session', json={'role': 'teacher', 'teacher_id': 7})
            teacher_headers = {'Authorization': 'Bearer ' + login.json()['access_token']}
            me = await self.client.get('/api/auth/me', headers=teacher_headers)
            self.assertIn({'capability': 'lead', 'scope': 'dept', 'scope_id': '视觉传达设计'}, me.json()['grants'])
            denied = await self.client.put('/api/teachers/7', headers=teacher_headers, json={'position': '教师'})
            self.assertEqual(denied.status_code, 403)
        await self.client.put('/api/teachers/7', headers=headers, json={'position': '教师'})
        me = await self.client.get('/api/auth/me', headers=teacher_headers)
        self.assertFalse(any(g['capability'] == 'lead' for g in me.json()['grants']))

    async def test_dean_positions_save_without_implicit_privileges(self):
        login = await self.client.post('/api/debug/session', json={'role': 'admin'})
        headers = {'Authorization': 'Bearer ' + login.json()['access_token']}
        for position in ['院长', '副院长']:
            response = await self.client.put('/api/teachers/7', headers=headers, json={'position': position})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['position'], position)
            records = await self.client.get('/api/teachers/', headers=headers)
            self.assertIn(position, records.text)
            self.assertEqual(position_grants(self.db.get(Teacher, 7)), [])

    async def test_missing_scope_and_invalid_position(self):
        login = await self.client.post('/api/debug/session', json={'role': 'admin'})
        headers = {'Authorization': 'Bearer ' + login.json()['access_token']}
        for payload in [{'position': '教研室主任'}, {'position': '管理员'}]:
            response = await self.client.put('/api/teachers/7', headers=headers, json=payload)
            self.assertEqual(response.status_code, 422, response.text)

    async def test_scope_is_exact_and_does_not_grant_publish(self):
        teacher = self.db.get(Teacher, 7)
        teacher.position = '教研室副主任'
        teacher.review_major = '视觉传达设计'
        user = SimpleNamespace(grants=position_grants(teacher), teacher_id=7)
        self.assertTrue(can(user, 'review', {'department': '视觉传达设计'}))
        self.assertFalse(can(user, 'review', {'department': '包装设计'}))
        self.assertFalse(can(user, 'publish', {'department': '视觉传达设计'}))

    async def test_real_bound_account_access_tracks_appointment(self):
        from app.models.user import User
        from app.models.planning import TeacherBinding, AccountGrant
        from app.services.auth import load_account_access
        user = User(username='bound', email='bound@test.invalid', password_hash='unused')
        self.db.add(user)
        self.db.flush()
        self.db.add(TeacherBinding(user_id=user.id, teacher_id=7))
        self.db.add(AccountGrant(user_id=user.id, capability='teaching', scope='self', scope_id=''))
        teacher = self.db.get(Teacher, 7)
        teacher.position, teacher.review_major = '教研室副主任', '包装设计'
        self.db.commit()
        self.assertTrue(can(load_account_access(user, self.db), 'review', {'department': '包装设计'}))
        teacher.position = '教师'
        self.db.commit()
        self.assertFalse(can(load_account_access(user, self.db), 'review', {'department': '包装设计'}))
        self.assertTrue(can(user, 'teaching', {'teacher_id': 7}))
