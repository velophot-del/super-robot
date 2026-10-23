import unittest
import test_debug_mode
from app.models.planning import CurriculumDocument


class CurriculumMaterialsRetirementTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown = test_debug_mode.DebugModeTests.asyncTearDown

    async def test_old_curriculum_rows_remain_stored_but_import_ui_api_is_removed(self):
        document = CurriculumDocument(name='archived plan.xlsx', major='Design', cohort='2026', revision=1,
            original=b'preserve this legacy source', sha256='legacy-hash', rows=[{'name': 'Old course'}])
        self.db.add(document)
        self.db.commit()
        token = (await self.client.post('/api/debug/session', json={'role': 'admin'})).json()['access_token']
        headers = {'Authorization': f'Bearer {token}'}

        for method, url in [
            ('GET', '/api/planning/curricula'),
            ('POST', '/api/planning/curricula/import'),
            ('POST', '/api/planning/curricula/1/activate'),
            ('GET', '/api/planning/curricula/1/source'),
        ]:
            response = await self.client.request(method, url, headers=headers)
            self.assertEqual(response.status_code, 404, f'{method} {url}: {response.text}')

        self.assertEqual(self.db.query(CurriculumDocument).one().original, b'preserve this legacy source')


if __name__ == '__main__':
    unittest.main()
