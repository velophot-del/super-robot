"""AI 排课分析：规则兜底、模型路径与管理员权限。"""
import unittest
from datetime import date, datetime
from unittest.mock import patch

import test_debug_mode
from app.config import settings
from app.models.planning import AcademicPlan
from app.models.user import User
from app.services import ai_config, ai_explanation
from app.services.auth import account_token, hash_password

CONTEXT = {
    'plan': {'name': '演示周期', 'state': 'matched', 'start_date': '2027-03-08', 'weeks': 20, 'group_count': 2},
    'stats': {'total': 3, 'placed': 2, 'with_slots': 1, 'with_room': 0, 'locked': 1},
    'issues': [
        {'task_id': 1, 'name': '构成设计', 'group': '视觉2601', 'category': 'missing_room',
         'level': 'blocking', 'message': '尚未落实上课地点'},
    ],
    'tasks_with_issues': [],
}


class FakeResponse:
    status_code = 200
    text = ''

    def json(self):
        return {'model': 'claude-opus-5-5', 'stop_reason': 'end_turn',
                'content': [{'type': 'text', 'text': '【总体判断】测试分析'}],
                'usage': {'input_tokens': 10, 'output_tokens': 20}}


class AiExplanationTests(unittest.TestCase):
    def test_rule_fallback_without_key(self):
        with patch.object(settings, 'ANTHROPIC_API_KEY', ''):
            result = ai_explanation.generate_ai_advice(CONTEXT)
        self.assertEqual(result['source'], 'rules')
        self.assertIn('【总体判断】', result['text'])
        self.assertIn('未配置 AI 服务', result['reason'])
        self.assertEqual(result['issue_count'], 1)

    def test_llm_path_returns_model_text(self):
        with patch.object(settings, 'ANTHROPIC_API_KEY', 'test-key'), \
             patch.object(ai_config.httpx, 'post', return_value=FakeResponse()) as post:
            result = ai_explanation.generate_ai_advice(CONTEXT)
        self.assertEqual(result['source'], 'llm')
        self.assertEqual(result['text'], '【总体判断】测试分析')
        self.assertEqual(result['model'], 'claude-opus-5-5')
        headers = post.call_args.kwargs['headers']
        self.assertEqual(headers['x-api-key'], 'test-key')
        self.assertEqual(headers['anthropic-version'], settings.ANTHROPIC_API_VERSION)
        self.assertEqual(post.call_args.kwargs['json']['fallbacks'], 'default')


class AiReviewEndpointTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown = test_debug_mode.DebugModeTests.asyncTearDown

    async def test_admin_gets_rule_analysis_and_others_are_rejected(self):
        self.db.add(AcademicPlan(id=1, name='AI 周期', start_date=date(2027, 3, 8), weeks=20,
                                 deadline=datetime(2027, 2, 1), state='draft', revision=1,
                                 settings={'major': '视觉传达设计', 'cohort': '2026', 'semester': 2}))
        denied = User(username='ai_denied', email='ai_denied@test.invalid',
                      password_hash=hash_password('Test123'))
        self.db.add(denied)
        self.db.commit()
        admin = (await self.client.post('/api/debug/session', json={'role': 'admin'})).json()['access_token']
        with patch.object(settings, 'ANTHROPIC_API_KEY', ''):
            response = await self.client.post('/api/planning/plans/1/ai-review',
                                              headers={'Authorization': f'Bearer {admin}'})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body['source'], 'rules')
        self.assertEqual(body['plan_id'], 1)
        self.assertEqual(body['issues'], [])
        self.assertIn('【总体判断】', body['text'])
        denied_response = await self.client.post(
            '/api/planning/plans/1/ai-review',
            headers={'Authorization': 'Bearer ' + account_token(denied, self.db)})
        self.assertEqual(denied_response.status_code, 403)

    async def test_ai_review_releases_read_transaction_before_model_call(self):
        self.db.add(AcademicPlan(id=2, name='AI 周期 2', start_date=date(2027, 3, 8), weeks=20,
                                 deadline=datetime(2027, 2, 1), state='draft', revision=1,
                                 settings={'major': '视觉传达设计', 'cohort': '2026', 'semester': 2}))
        self.db.commit()
        admin = (await self.client.post('/api/debug/session', json={'role': 'admin'})).json()['access_token']

        def fake_call(*args, **kwargs):
            self.assertFalse(self.db.in_transaction())
            return {'text': '【总体判断】模型结果', 'model': 'test-model', 'usage': {}}

        with patch.object(settings, 'ANTHROPIC_API_KEY', 'test-key'), \
             patch('app.services.ai_explanation.call_llm', side_effect=fake_call):
            response = await self.client.post('/api/planning/plans/2/ai-review',
                                              headers={'Authorization': f'Bearer {admin}'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['source'], 'llm')
        self.assertEqual(response.json()['text'], '【总体判断】模型结果')
