from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Values come from the environment, never the repo."""

    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "local"
    app_base_url: str = "http://localhost:8001"
    database_url: str = "sqlite:///./payments.db"

    cashfree_mode: str = "sandbox"
    cashfree_base_url: str = "https://sandbox.cashfree.com/pg"
    cashfree_client_id: str = ""
    cashfree_client_secret: str = ""
    cashfree_api_version: str = "2023-08-01"

    chaos_token: str = ""
    chaos_max_requests: int = 50
    chaos_ttl_seconds: int = 600

    runbook_url: str = ""
