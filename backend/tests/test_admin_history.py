from datetime import date, datetime
import unittest
import test_debug_mode
from app.models.planning import AcademicPlan, PublishedPlan, AccountGrant
from app.models.user import User
from app.services.auth import hash_password, account_token


class AdminHistoryTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown = test_debug_mode.DebugModeTests.asyncTearDown

    async def test_latest_published_snapshots_only_and_admin_required(self):
        for pid in [1, 2, 3]:
            self.db.add(AcademicPlan(id=pid, name=f'Cycle {pid}', start_date=date(2027, 2, 1), weeks=20, deadline=datetime(2027, 1, 1), state='draft'))
        self.db.flush()
        for pid, label in [(1, 'old'), (1, 'latest'), (2, 'second')]:
            self.db.add(PublishedPlan(plan_id=pid, payload={'plan': {'id': pid, 'weeks': 20}, 'tasks': [{'name': label}]}))
            self.db.flush()
        admin = User(username='history_admin', email='history@test.invalid', password_hash=hash_password('Test123'))
        denied = User(username='history_denied', email='denied@test.invalid', password_hash=hash_password('Test123'))
        self.db.add_all([admin, denied]); self.db.flush()
        self.db.add(AccountGrant(user_id=admin.id, capability='admin', scope='all', scope_id=''))
        self.db.commit()
        response = await self.client.get('/api/planning/history/published', headers={'Authorization': 'Bearer '+account_token(admin, self.db)})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([row['tasks'][0]['name'] for row in response.json()], ['second', 'latest'])
        response = await self.client.get('/api/planning/history/published', headers={'Authorization': 'Bearer '+account_token(denied, self.db)})
        self.assertEqual(response.status_code, 403)
        self.assertEqual((await self.client.get('/api/planning/history/published')).status_code, 401)
