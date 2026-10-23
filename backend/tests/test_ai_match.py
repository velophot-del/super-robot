"""AI 排序参与教师-课程匹配：排序落位、规则兜底与配置要求。"""
import unittest
from unittest.mock import patch

import test_debug_mode
from app.config import settings


class AIMatchTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_debug_mode.DebugModeTests.asyncSetUp
    asyncTearDown = test_debug_mode.DebugModeTests.asyncTearDown

    async def headers(self, role='admin'):
        data = {'role': role}
        if role == 'teacher':
            data['teacher_id'] = 7
        response = await self.client.post('/api/debug/session', json=data)
        headers = {'Authorization': 'Bearer ' + response.json()['access_token']}
        if role == 'teacher':
            profile = (await self.client.get('/api/planning/self-profile', headers=headers)).json()
            if not profile['ready']:
                await self.client.put('/api/planning/self-profile', headers=headers, json={
                    'revision': profile['revision'], 'direction': 'Design',
                    'tags': ['type'], 'skilled_courses': ['Typography']})
        return headers

    async def prepare_match(self):
        from app.models.classroom import Classroom
        if not self.db.get(Classroom, 31):
            self.db.add(Classroom(id=31, name='Room', room_code='R31', capacity=40))
            self.db.commit()
        admin = await self.headers()
        teacher = await self.headers('teacher')
        plan = await self.client.post('/api/planning/plans', headers=admin, json={
            'name': 'AI match', 'start_date': '2027-02-01', 'weeks': 20,
            'deadline': '2027-01-31T23:59:59', 'rule_confirmed': True})
        pid = plan.json()['id']
        task = await self.client.post(f'/api/planning/plans/{pid}/tasks', headers=admin, json={
            'name': 'Typography', 'code': 'A', 'group': 'Class A', 'department': 'Design',
            'credits': 1.5, 'required_hours': 8, 'start_week': 1, 'end_week': 2,
            'direction': 'Design', 'tags': ['type'], 'profile_verified': True,
            'slots': [{'day': 1, 'start': 1, 'count': 4}], 'teacher_count': 1, 'room_id': 31})
        task_id = task.json()['id']
        await self.client.put('/api/planning/profiles/7', headers=admin, json={
            'direction': 'Design', 'tags': ['type'], 'verified': True,
            'team_codes': ['A'], 'taught_codes': ['A'], 'weekly_limit': 20, 'course_limit': 3})
        await self.client.post(f'/api/planning/plans/{pid}/open', headers=admin)
        state = (await self.client.get(f'/api/planning/plans/{pid}', headers=teacher)).json()
        draft = await self.client.put(f'/api/planning/plans/{pid}/draft', headers=teacher,
            json={'revision': 0, 'plan_revision': state['revision'], 'task_ids': [task_id]})
        await self.client.post(f'/api/planning/plans/{pid}/submit', headers=teacher,
            json={'revision': draft.json()['revision']})
        return pid, task_id, admin

    def save_ai_config(self):
        from app.models.ai_config import AIConfig
        from app.services.ai_config import encrypt_key
        self.db.add(AIConfig(id=1, provider='deepseek', base_url='https://api.deepseek.com',
                             model='deepseek-chat', api_key_encrypted=encrypt_key('sk-test'),
                             enabled=True))
        self.db.commit()

    async def test_ai_ranking_is_applied_and_constraints_hold(self):
        pid, task_id, admin = await self.prepare_match()
        self.save_ai_config()
        text = '{"rankings":[{"task_id":%d,"teacher_ids":[7],"reason":"方向匹配"}]}' % task_id
        with patch('app.api.planning.call_llm',
                   return_value={'text': text, 'model': 'deepseek-chat', 'usage': {}}):
            matched = await self.client.post(f'/api/planning/plans/{pid}/match',
                                             headers=admin, params={'use_ai': 'true'})
        self.assertEqual(matched.status_code, 200, matched.text)
        body = matched.json()
        self.assertTrue(body['ai_used'])
        self.assertTrue(body['ai_applied'])
        self.assertEqual(body['auto_assigned'], 1)
        self.assertEqual(body['suggestions'][0]['teacher_ids'], [7])
        self.assertEqual(body['suggestions'][0]['source'], 'ai')
        state = (await self.client.get(f'/api/planning/plans/{pid}', headers=admin)).json()
        self.assertEqual(state['state'], 'matched')
        self.assertEqual(state['tasks'][0]['teacher_ids'], [7])

    async def test_ai_match_requires_config(self):
        pid, _task_id, admin = await self.prepare_match()
        with patch.object(settings, 'ANTHROPIC_API_KEY', ''):
            matched = await self.client.post(f'/api/planning/plans/{pid}/match',
                                             headers=admin, params={'use_ai': 'true'})
        self.assertEqual(matched.status_code, 409)
        self.assertIn('AI 设置', matched.text)

    async def test_invalid_ai_json_falls_back_to_rules(self):
        pid, _task_id, admin = await self.prepare_match()
        self.save_ai_config()
        with patch('app.api.planning.call_llm',
                   return_value={'text': '不是 JSON', 'model': 'deepseek-chat'}):
            matched = await self.client.post(f'/api/planning/plans/{pid}/match',
                                             headers=admin, params={'use_ai': 'true'})
        self.assertEqual(matched.status_code, 200, matched.text)
        body = matched.json()
        self.assertFalse(body['ai_used'])
        self.assertFalse(body['ai_applied'])
        self.assertEqual(body['auto_assigned'], 1)
        self.assertEqual(body['suggestions'][0]['teacher_ids'], [7])
        self.assertEqual(body['suggestions'][0]['source'], 'rule')
