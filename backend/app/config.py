"""应用配置模块"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """应用配置"""
    APP_NAME: str = "AI智能排课平台"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    DEBUG_DEMO_MODE: bool = False
    DEBUG_DEMO_DATABASE_URL: str = ""

    # JWT 签名密钥。生产环境必须通过环境变量 SECRET_KEY 提供；
    # 开发环境留空时会在 backend/data/jwt_secret.key 生成并持久化一个随机密钥。
    SECRET_KEY: str = ""

    # 数据库配置 - 使用SQLite便于开发
    DATABASE_URL: str = "sqlite:///./data/scheduling.db"

    # 排课参数默认值
    MAX_GENERATIONS: int = 500
    POPULATION_SIZE: int = 100
    MUTATION_RATE: float = 0.1
    CROSSOVER_RATE: float = 0.8

    # 每周上课天数（默认周一至周五）
    WEEKDAYS: int = 5
    # 每天上课节数（默认8节）
    PERIODS_PER_DAY: int = 8

    # AI 排课分析（可选）。未配置 ANTHROPIC_API_KEY 时自动回退到规则分析。
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-opus-5-5"
    ANTHROPIC_BASE_URL: str = "https://api.anthropic.com"
    ANTHROPIC_API_VERSION: str = "2026-10-21"
    AI_TIMEOUT_SECONDS: float = 30.0

    # CORS配置
    CORS_ORIGINS: list = ["http://localhost:5173", "http://localhost:3000"]

    model_config = {"env_file": ".env", "case_sensitive": True}


settings = Settings()
