"""AI 服务配置管理：服务商、模型、加密密钥与连通性测试。"""
import time
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.ai_config import AIConfig
from app.services.ai_config import (LLMError, PROVIDERS, call_llm, decrypt_key,
                                    encrypt_key, mask_key, protocol_for, resolve_config)
from app.services.auth import require_user
from app.services.authorization import check

router = APIRouter(prefix='/api/ai', tags=['AI 配置'])

ProviderName = Literal['deepseek', 'qwen', 'moonshot', 'zhipu', 'custom', 'anthropic']


class AIConfigInput(BaseModel):
    provider: ProviderName
    base_url: str = Field(min_length=1, max_length=300)
    model: str = Field(min_length=1, max_length=100)
    api_key: str = Field('', max_length=500)
    enabled: bool = True
    clear_key: bool = False

    @model_validator(mode='after')
    def normalize(self):
        self.base_url = self.base_url.strip()
        self.model = self.model.strip()
        if not self.base_url.startswith(('http://', 'https://')):
            raise ValueError('接口地址必须以 http:// 或 https:// 开头')
        return self


class AITestInput(BaseModel):
    provider: ProviderName | None = None
    base_url: str | None = None
    model: str | None = None
    api_key: str = Field('', max_length=500)


def _config_response(db):
    row = db.get(AIConfig, 1)
    effective = resolve_config(db)
    if row is not None:
        key = decrypt_key(row.api_key_encrypted) if row.api_key_encrypted else ''
        return {'provider': row.provider, 'base_url': row.base_url, 'model': row.model,
                'enabled': row.enabled, 'configured': bool(row.api_key_encrypted),
                'masked_key': mask_key(key), 'source': effective['source'] if effective else 'none',
                'providers': PROVIDERS, 'updated_by': row.updated_by,
                'updated_at': row.updated_at.isoformat() if row.updated_at else None}
    env_key = (settings.ANTHROPIC_API_KEY or '').strip()
    if env_key:
        return {'provider': 'anthropic', 'base_url': settings.ANTHROPIC_BASE_URL,
                'model': settings.ANTHROPIC_MODEL, 'enabled': True, 'configured': True,
                'masked_key': mask_key(env_key), 'source': 'env', 'providers': PROVIDERS,
                'updated_by': None, 'updated_at': None}
    preset = PROVIDERS['deepseek']
    return {'provider': 'deepseek', 'base_url': preset['base_url'], 'model': preset['model'],
            'enabled': True, 'configured': False, 'masked_key': '', 'source': 'none',
            'providers': PROVIDERS, 'updated_by': None, 'updated_at': None}


@router.get('/config')
def get_config(user=Depends(require_user), db: Session = Depends(get_db)):
    check(user, 'admin')
    return _config_response(db)


@router.put('/config')
def save_config(data: AIConfigInput, user=Depends(require_user), db: Session = Depends(get_db)):
    check(user, 'admin')
    row = db.get(AIConfig, 1)
    if row is None:
        row = AIConfig(id=1)
        db.add(row)
    row.provider = data.provider
    row.base_url = data.base_url
    row.model = data.model
    row.enabled = data.enabled
    if data.api_key.strip():
        row.api_key_encrypted = encrypt_key(data.api_key.strip())
    elif data.clear_key:
        row.api_key_encrypted = None
    row.updated_by = f"{'demo' if getattr(user, 'is_demo', False) else 'user'}:{user.id}"
    db.commit()
    db.refresh(row)
    return _config_response(db)


@router.post('/config/test')
def test_config(data: AITestInput, user=Depends(require_user), db: Session = Depends(get_db)):
    check(user, 'admin')
    row = db.get(AIConfig, 1)
    provider = data.provider or (row.provider if row else 'deepseek')
    preset = PROVIDERS.get(provider, PROVIDERS['custom'])
    base_url = (data.base_url or (row.base_url if row else preset['base_url']) or '').strip()
    model = (data.model or (row.model if row else preset['model']) or '').strip()
    key = data.api_key.strip()
    if not key and row and row.api_key_encrypted:
        key = decrypt_key(row.api_key_encrypted)
    if not key:
        return {'ok': False, 'message': '请先填写 API Key'}
    if not base_url:
        return {'ok': False, 'message': '请填写接口地址'}
    if not model:
        return {'ok': False, 'message': '请填写模型名称'}
    config = {'provider': provider, 'protocol': protocol_for(provider),
              'base_url': base_url, 'model': model, 'api_key': key}
    start = time.monotonic()
    try:
        result = call_llm(config, '你是连通性测试助手，只回复 OK。', 'ping', max_tokens=16)
        return {'ok': True, 'message': '连接成功', 'model': result.get('model') or model,
                'latency_ms': int((time.monotonic() - start) * 1000)}
    except LLMError as exc:
        return {'ok': False, 'message': str(exc),
                'latency_ms': int((time.monotonic() - start) * 1000)}
