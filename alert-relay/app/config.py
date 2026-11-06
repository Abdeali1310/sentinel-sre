from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    mattermost_webhook_url: str = ""
    mattermost_channel: str = "#incidents"
    bot_display_name: str = "Sentinel"
    runbook_url: str = ""
