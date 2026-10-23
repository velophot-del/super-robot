"""AI 配置接口：密钥加密/掩码、保留与清除、连通性测试和管理员权限。"""
import json
import unittest
from unittest.mock import patch

import test_debug_mode
from app.api import ai_settings
from app.models.ai_config import AIConfig
from app.models.user import User
from app.services.auth import account_token, hash_password


class AIConfigTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown = test_debug_mode.DebugModeTests.asyncTearDown

    async def admin_headers(self):
        token = (await self.client.post('/api/debug/session', json={'role': 'admin'})).json()['access_token']
        return {'Authorization': f'Bearer {token}'}

    async def test_key_is_masked_kept_and_clearable(self):
        headers = await self.admin_headers()
        payload = {'provider': 'deepseek', 'base_url': 'https://api.deepseek.com',
                   'model': 'deepseek-chat', 'api_key': 'sk-test-secret-1234', 'enabled': True}
        saved = await self.client.put('/api/ai/config', headers=headers, json=payload)
        self.assertEqual(saved.status_code, 200, saved.text)
        body = saved.json()
        self.assertTrue(body['configured'])
        self.assertNotIn('sk-test-secret-1234', json.dumps(body, ensure_ascii=False))
        self.assertIn('…', body['masked_key'])
        self.assertTrue(body['updated_at'].endswith('Z'))
        row = self.db.get(AIConfig, 1)
        self.assertNotEqual(row.api_key_encrypted, 'sk-test-secret-1234')

        kept = await self.client.put('/api/ai/config', headers=headers, json={**payload, 'api_key': ''})
        self.assertTrue(kept.json()['configured'])

        cleared = await self.client.put('/api/ai/config', headers=headers,
                                        json={**payload, 'api_key': '', 'clear_key': True})
        self.assertFalse(cleared.json()['configured'])
        self.assertIsNone(self.db.get(AIConfig, 1).api_key_encrypted)

    async def test_test_endpoint_requires_key_and_reports_success(self):
        headers = await self.admin_headers()
        response = await self.client.post('/api/ai/config/test', headers=headers, json={
            'provider': 'deepseek', 'base_url': 'https://api.deepseek.com',
            'model': 'deepseek-chat', 'api_key': ''})
        self.assertFalse(response.json()['ok'])
        self.assertIn('API Key', response.json()['message'])
        with patch.object(ai_settings, 'call_llm',
                          return_value={'text': 'OK', 'model': 'deepseek-chat'}) as mocked:
            tested = await self.client.post('/api/ai/config/test', headers=headers, json={
                'provider': 'deepseek', 'base_url': 'https://api.deepseek.com',
                'model': 'deepseek-chat', 'api_key': 'sk-test'})
        self.assertTrue(tested.json()['ok'], tested.text)
        self.assertEqual(tested.json()['model'], 'deepseek-chat')
        self.assertEqual(mocked.call_args.kwargs.get('max_tokens'), 512)
        self.assertEqual(mocked.call_args.kwargs.get('effort'), 'low')

    def test_provider_response_shape_errors_become_llm_error(self):
        from app.services import ai_config

        class BadResponse:
            status_code = 200
            text = ''

            def json(self):
                return ['not', 'a', 'dict']

        with patch.object(ai_config.httpx, 'post', return_value=BadResponse()):
            with self.assertRaises(ai_config.LLMError):
                ai_config.call_llm({'protocol': 'openai', 'base_url': 'https://example.invalid',
                                    'model': 'm', 'api_key': 'k'}, 'system', 'user')

    def test_openai_list_content_is_joined(self):
        from app.services import ai_config

        class ListResponse:
            status_code = 200
            text = ''

            def json(self):
                return {'model': 'm', 'choices': [{'message': {'content': [
                    {'type': 'text', 'text': 'O'}, {'type': 'text', 'text': 'K'}]}}]}

        with patch.object(ai_config.httpx, 'post', return_value=ListResponse()):
            result = ai_config.call_llm({'protocol': 'openai', 'base_url': 'https://example.invalid',
                                         'model': 'm', 'api_key': 'k'}, 'system', 'user')
        self.assertEqual(result['text'], 'OK')

    async def test_non_admin_cannot_read_or_write(self):
        denied = User(username='ai_cfg_denied', email='ai_cfg_denied@test.invalid',
                      password_hash=hash_password('Test123'))
        self.db.add(denied)
        self.db.commit()
        headers = {'Authorization': 'Bearer ' + account_token(denied, self.db)}
        self.assertEqual((await self.client.get('/api/ai/config', headers=headers)).status_code, 403)
        self.assertEqual((await self.client.put('/api/ai/config', headers=headers, json={
            'provider': 'deepseek', 'base_url': 'https://api.deepseek.com',
            'model': 'deepseek-chat', 'api_key': 'x'})).status_code, 403)
