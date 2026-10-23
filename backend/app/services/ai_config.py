"""AI 服务商配置、密钥加解密与统一模型调用。

数据库配置优先；未配置时回退到环境变量中的 Anthropic 配置。
密钥使用由 SECRET_KEY 派生的 Fernet 密钥加密后落库，接口只返回掩码。
"""
import base64
import hashlib
import logging

import httpx
from cryptography.fernet import Fernet, InvalidToken

from app.config import settings
from app.models.ai_config import AIConfig
from app.services.auth import SECRET_KEY

logger = logging.getLogger(__name__)

PROVIDERS = {
    'deepseek': {'label': 'DeepSeek', 'base_url': 'https://api.deepseek.com',
                 'model': 'deepseek-chat', 'protocol': 'openai'},
    'qwen': {'label': '通义千问', 'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
             'model': 'qwen-plus', 'protocol': 'openai'},
    'moonshot': {'label': '月之暗面 Kimi', 'base_url': 'https://api.moonshot.cn/v1',
                 'model': 'moonshot-v1-8k', 'protocol': 'openai'},
    'zhipu': {'label': '智谱 GLM', 'base_url': 'https://open.bigmodel.cn/api/paas/v4',
              'model': 'glm-4-flash', 'protocol': 'openai'},
    'custom': {'label': '自定义 OpenAI 兼容', 'base_url': '', 'model': '', 'protocol': 'openai'},
    'anthropic': {'label': 'Anthropic Claude', 'base_url': 'https://api.anthropic.com',
                  'model': 'claude-opus-5-5', 'protocol': 'anthropic'},
}


class LLMError(Exception):
    """模型调用失败；消息可直接展示给管理员。"""


def _fernet():
    key = base64.urlsafe_b64encode(hashlib.sha256(SECRET_KEY.encode('utf-8')).digest())
    return Fernet(key)


def encrypt_key(value):
    return _fernet().encrypt(value.encode('utf-8')).decode('utf-8')


def decrypt_key(value):
    if not value:
        return ''
    try:
        return _fernet().decrypt(value.encode('utf-8')).decode('utf-8')
    except (InvalidToken, ValueError, TypeError):
        return ''


def mask_key(value):
    if not value:
        return ''
    if len(value) <= 8:
        return '••••'
    return f'{value[:3]}…{value[-4:]}'


def protocol_for(provider):
    return PROVIDERS.get(provider, PROVIDERS['custom'])['protocol']


def resolve_config(db=None):
    """数据库配置优先；数据库未启用或未配置密钥时回退到环境变量。"""
    row = db.get(AIConfig, 1) if db is not None else None
    if row is not None:
        if not row.enabled:
            return None
        key = decrypt_key(row.api_key_encrypted) if row.api_key_encrypted else ''
        if key:
            provider = row.provider if row.provider in PROVIDERS else 'custom'
            return {'provider': provider, 'protocol': protocol_for(provider),
                    'base_url': row.base_url, 'model': row.model, 'api_key': key,
                    'source': 'database'}
    env_key = (settings.ANTHROPIC_API_KEY or '').strip()
    if env_key:
        return {'provider': 'anthropic', 'protocol': 'anthropic',
                'base_url': settings.ANTHROPIC_BASE_URL, 'model': settings.ANTHROPIC_MODEL,
                'api_key': env_key, 'source': 'env'}
    return None


def _status_message(status):
    if status in (401, 403):
        return 'API Key 无效或无权访问'
    if status == 404:
        return 'AI 接口地址或模型不存在'
    if status == 429:
        return 'AI 服务请求过于频繁'
    return f'AI 服务返回 {status}'


def call_llm(config, system, user_text, max_tokens=2000, json_mode=False, effort='medium'):
    """按服务商协议发起一次非流式调用；失败统一抛出 LLMError。"""
    protocol = config.get('protocol') or protocol_for(config.get('provider', 'custom'))
    try:
        if protocol == 'anthropic':
            return _call_anthropic(config, system, user_text, max_tokens, effort)
        return _call_openai(config, system, user_text, max_tokens, json_mode)
    except httpx.TimeoutException as exc:
        raise LLMError('AI 服务超时') from exc
    except httpx.RequestError as exc:
        raise LLMError('AI 服务连接失败') from exc


def _openai_text(content):
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and part.get('type') in (None, 'text'):
                text = part.get('text')
                if isinstance(text, str):
                    parts.append(text)
        return ''.join(parts).strip()
    return ''


def _call_openai(config, system, user_text, max_tokens, json_mode):
    base = (config.get('base_url') or '').rstrip('/')
    if not base:
        raise LLMError('未填写 AI 接口地址')
    body = {
        'model': config.get('model') or '',
        'messages': [{'role': 'system', 'content': system},
                     {'role': 'user', 'content': user_text}],
        'max_tokens': max_tokens,
    }
    if json_mode:
        body['response_format'] = {'type': 'json_object'}
    response = httpx.post(
        base + '/chat/completions',
        headers={'Authorization': f"Bearer {config.get('api_key', '')}",
                 'Content-Type': 'application/json'},
        json=body, timeout=settings.AI_TIMEOUT_SECONDS,
    )
    if response.status_code != 200:
        logger.warning('AI provider status=%s body=%s', response.status_code, response.text[:200])
        raise LLMError(_status_message(response.status_code))
    try:
        payload = response.json()
    except ValueError as exc:
        raise LLMError('AI 服务返回无法解析') from exc
    if not isinstance(payload, dict):
        raise LLMError('AI 服务返回格式不正确')
    choices = payload.get('choices')
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise LLMError('AI 未返回文本')
    message = choices[0].get('message')
    text = _openai_text(message.get('content')) if isinstance(message, dict) else ''
    if not text:
        raise LLMError('AI 未返回文本')
    model = payload.get('model')
    usage = payload.get('usage')
    return {'text': text, 'model': model if isinstance(model, str) and model else config.get('model') or '',
            'usage': usage if isinstance(usage, dict) else {}}


def _call_anthropic(config, system, user_text, max_tokens, effort='medium'):
    base = (config.get('base_url') or settings.ANTHROPIC_BASE_URL).rstrip('/')
    if base.endswith('/v1'):
        base = base[:-3]
    body = {
        'model': config.get('model') or settings.ANTHROPIC_MODEL,
        'max_tokens': max_tokens,
        'system': system,
        'messages': [{'role': 'user', 'content': user_text}],
        'output_config': {'effort': effort},
        'fallbacks': 'default',
    }
    response = httpx.post(
        base + '/v1/messages',
        headers={'content-type': 'application/json',
                 'x-api-key': config.get('api_key', ''),
                 'anthropic-version': settings.ANTHROPIC_API_VERSION,
                 'anthropic-beta': 'server-side-fallback-2026-07-01'},
        json=body, timeout=settings.AI_TIMEOUT_SECONDS,
    )
    if response.status_code != 200:
        logger.warning('Anthropic status=%s body=%s', response.status_code, response.text[:200])
        raise LLMError(_status_message(response.status_code))
    try:
        payload = response.json()
    except ValueError as exc:
        raise LLMError('AI 服务返回无法解析') from exc
    if not isinstance(payload, dict):
        raise LLMError('AI 服务返回格式不正确')
    if payload.get('stop_reason') == 'refusal':
        raise LLMError('AI 拒绝了本次分析')
    blocks = payload.get('content')
    if not isinstance(blocks, list):
        raise LLMError('AI 未返回文本')
    text = '\n'.join(block.get('text', '') for block in blocks
                     if isinstance(block, dict) and block.get('type') == 'text').strip()
    if not text:
        raise LLMError('AI 未返回文本')
    model = payload.get('model')
    usage = payload.get('usage')
    return {'text': text,
            'model': model if isinstance(model, str) and model else settings.ANTHROPIC_MODEL,
            'usage': usage if isinstance(usage, dict) else {}}
