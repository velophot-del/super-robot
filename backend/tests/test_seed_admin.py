import unittest
import test_debug_mode
from app.seed_admin import seed_admin, CAPABILITIES
from app.models.user import User
from app.services.auth import hash_password, verify_password


class SeedAdminTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown = test_debug_mode.DebugModeTests.asyncTearDown

    async def test_seed_login_and_repeat_preserves_password(self):
        user, created = seed_admin(self.db, 'admin_2026')
        self.db.commit()
        self.assertTrue(created)
        original_hash = user.password_hash
        _, created = seed_admin(self.db, 'different-password')
        self.db.commit()
        self.assertFalse(created)
        self.assertEqual(user.password_hash, original_hash)
        response = await self.client.post('/api/auth/login', json={'username': 'admin', 'password': 'admin_2026'})
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual({g['capability'] for g in data['user']['grants']}, set(CAPABILITIES))
        headers = {'Authorization': 'Bearer ' + data['access_token']}
        for path in ['/api/teachers/', '/api/planning/plans']:
            self.assertEqual((await self.client.get(path, headers=headers)).status_code, 200)

    async def test_existing_account_is_not_claimed(self):
        self.db.add(User(username='admin', email='existing@test.com', password_hash=hash_password('existing')))
        self.db.commit()
        with self.assertRaises(ValueError):
            seed_admin(self.db, 'admin_2026')
        self.assertTrue(verify_password('existing', self.db.query(User).filter_by(username='admin').one().password_hash))
