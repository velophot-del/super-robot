"""AI 服务配置（单行记录，密钥加密保存）。"""
from sqlalchemy import Boolean, Column, Integer, String

from app.database import Base
from app.models.base import TimestampMixin


class AIConfig(Base, TimestampMixin):
    __tablename__ = 'ai_config'

    id = Column(Integer, primary_key=True)
    provider = Column(String(30), nullable=False, default='deepseek')
    base_url = Column(String(300), nullable=False, default='https://api.deepseek.com')
    model = Column(String(100), nullable=False, default='deepseek-chat')
    api_key_encrypted = Column(String(1000), nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    updated_by = Column(String(120), nullable=True)
