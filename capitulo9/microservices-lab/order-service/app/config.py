from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EVENTSTORE_", extra="ignore")
    database_url: str = "postgresql+asyncpg://order_app:order_app_lab_pass@localhost:5432/eventstore_db"
    snapshot_threshold: int = Field(default=10, ge=1)
    admin_key: str = "lab-admin-key"
