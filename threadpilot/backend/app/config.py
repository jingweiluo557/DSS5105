"""场景 1.1–3.3：统一环境配置。"""
from pathlib import Path
from typing import Literal
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / 'backend/.env', extra='ignore')
    database_url: SecretStr = SecretStr('mysql+pymysql://threadpilot@127.0.0.1:3306/threadpilot')
    ai_database_url: SecretStr = SecretStr('')
    openai_api_key: SecretStr = SecretStr('')
    openai_base_url: str | None = None
    openai_model: str = 'gpt-4.1'
    intent_api_style: Literal['responses', 'chat_completions'] = 'responses'
    openai_timeout_seconds: float = 60
    openai_max_retries: int = Field(default=2, ge=0, le=5)      # bounded retries on rate limits, 5xx and dropped connections
    chat_requests_per_minute: int = Field(default=40, ge=0)     # per client, on endpoints that call the model; 0 turns it off
    data_api_token: SecretStr = SecretStr('')
    sync_enabled: bool = False
    sync_interval_minutes: int = Field(default=5, ge=1)
    sync_files: list[str] = []
    raw_data_dir: Path = ROOT / 'data/raw'
    max_upload_bytes: int = Field(default=10_485_760, ge=1024)
    sql_max_rows: int = Field(default=100, ge=1, le=1000)
    sql_timeout_ms: int = Field(default=5000, ge=100, le=60000)
    sql_agent_steps: int = Field(default=16, ge=4, le=50)
    workflow_db: Path = ROOT / 'backend/runtime/workflow.sqlite3'
    cors_origins: list[str] = ['http://127.0.0.1:8765', 'http://localhost:8765', 'http://127.0.0.1:8000', 'http://localhost:8000']
    business_now: str = 'live'
    workflow_storage: Literal['sqlite', 'database'] = 'sqlite'
    background_tasks_enabled: bool = True
    serve_frontend: bool = True
    api_access_token: SecretStr = SecretStr('')
    scheduler_token: SecretStr = SecretStr('')
    morning_scheduler_enabled: bool = False
    briefing_email_to: str = ''                                 # comma-separated default recipients for the morning email
