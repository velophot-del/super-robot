import unittest
from unittest.mock import patch

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models.teacher import Teacher


class DebugModeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_engine('sqlite://', poolclass=StaticPool,
                                    connect_args={'check_same_thread': False})
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.db.add(Teacher(id=7, name='Demo teacher', teacher_code='TEST-7'))
        self.db.commit()

        def database():
            yield self.db

        app.dependency_overrides[get_db] = database
        self.flags = patch.dict(settings.__dict__, DEBUG_DEMO_MODE=True,
                                DEBUG_DEMO_DATABASE_URL=settings.DATABASE_URL)
        self.flags.start()
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=('127.0.0.1', 1234)),
            base_url='http://localhost')

    async def asyncTearDown(self):
        await self.client.aclose()
        self.flags.stop()
        app.dependency_overrides.clear()
        self.db.close()
        self.engine.dispose()

    async def test_switch_identity_and_validate_teacher(self):
        response = await self.client.get('/api/debug/identities')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['teachers'][0]['id'], 7)
        for role, teacher_id in [('admin', None), ('teacher', 7)]:
            response = await self.client.post('/api/debug/session', json={
                'role': role, 'teacher_id': teacher_id})
            self.assertEqual(response.status_code, 200)
            token = response.json()['access_token']
            me = await self.client.get('/api/auth/me', headers={
                'Authorization': f'Bearer {token}'})
            self.assertEqual(me.status_code, 200)
            self.assertEqual(me.json()['role'], role)
            self.assertEqual(me.json()['teacher_id'], teacher_id)
            self.assertTrue(me.json()['is_demo'])
        bad = await self.client.post('/api/debug/session', json={
            'role': 'teacher', 'teacher_id': 999})
        self.assertEqual(bad.status_code, 404)
        missing = await self.client.post('/api/debug/session', json={'role': 'teacher'})
        self.assertEqual(missing.status_code, 422)

    async def test_disabled_mode_revokes_demo_token_and_keeps_login_required(self):
        response = await self.client.post('/api/debug/session', json={'role': 'admin'})
        self.assertEqual(response.status_code, 200)
        token = response.json()['access_token']
        with patch.object(settings, 'DEBUG_DEMO_MODE', False):
            status = await self.client.get('/api/debug/status')
            self.assertFalse(status.json()['enabled'])
            self.assertEqual((await self.client.post('/api/debug/session',
                             json={'role': 'admin'})).status_code, 404)
            self.assertEqual((await self.client.get('/api/auth/me', headers={
                'Authorization': f'Bearer {token}'})).status_code, 401)
        self.assertEqual((await self.client.get('/api/auth/me')).status_code, 401)

    async def test_wrong_database_and_remote_request_cannot_enable_demo(self):
        with patch.object(settings, 'DEBUG_DEMO_DATABASE_URL', 'sqlite:///other.db'):
            self.assertEqual((await self.client.post('/api/debug/session',
                             json={'role': 'admin'})).status_code, 404)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(
                app=app, client=('192.0.2.1', 1234)), base_url='http://localhost') as remote:
            self.assertEqual((await remote.post('/api/debug/session',
                             json={'role': 'admin'})).status_code, 404)
        self.assertEqual((await self.client.post('/api/debug/session',
                         json={'role': 'root'})).status_code, 422)

    async def test_normal_login_still_works_without_demo_mode(self):
        with patch.object(settings, 'DEBUG_DEMO_MODE', False):
            from app.models.user import User
            from app.services.auth import hash_password
            self.db.add(User(username='normal_user',email='normal@example.com',password_hash=hash_password('TestPassword123')))
            self.db.commit()
            logged_in = await self.client.post('/api/auth/login', json={
                'username': 'normal_user', 'password': 'TestPassword123'})
            self.assertEqual(logged_in.status_code, 200)
            response = await self.client.get('/api/auth/me', headers={
                'Authorization': f"Bearer {logged_in.json()['access_token']}"})
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.json()['is_demo'])
            self.assertEqual(response.json()['role'], 'user')
