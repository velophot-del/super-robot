import unittest
import test_debug_mode


class CurriculumImportRetirementTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown = test_debug_mode.DebugModeTests.asyncTearDown

    async def test_curriculum_upload_activation_and_sync_routes_are_not_exposed(self):
        token = (await self.client.post('/api/debug/session', json={'role': 'admin'})).json()['access_token']
        headers = {'Authorization': f'Bearer {token}'}
        for method, url in [
            ('GET', '/api/planning/curricula'),
            ('POST', '/api/planning/curricula/import'),
            ('POST', '/api/planning/curricula/1/activate'),
            ('POST', '/api/planning/curricula/1/sync-courses'),
            ('GET', '/api/planning/curricula/1/source'),
            ('POST', '/api/planning/plans/1/sync-course-pool'),
        ]:
            response = await self.client.request(method, url, headers=headers)
            self.assertEqual(response.status_code, 404, f'{method} {url}: {response.text}')


if __name__ == '__main__':
    unittest.main()
