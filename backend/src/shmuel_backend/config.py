from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    cors_origins: list[str] = ["http://localhost:5173"]
    database_url: str = "postgresql+asyncpg://localhost/shmuel"

    # Fernet key for encrypting OAuth refresh tokens at rest.
    # See .env.example for the generation command.
    encryption_key: str = ""

    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_oauth_redirect_uri: str = "http://localhost:8000/auth/google/callback"
    admin_redirect_uri: str = "http://localhost:5173/settings"

    # Sentry DSN for production error tracking. Empty = disabled (dev/CI default).
    sentry_dsn: str = ""

    # Same value the api-proxy Cloudflare Worker checks. Defense-in-depth so
    # direct hits to the .run.app URL (bypassing the Worker) also require it.
    # Empty disables the check (dev default).
    backend_api_key: str = ""

    # Scheduler — Asia/Jerusalem times. Configurable later via a settings UI.
    schedule_tz: str = "Asia/Jerusalem"
    schedule_morning_slot: str = "08:00"
    schedule_evening_slot: str = "20:00"
    schedule_posts_per_slot: int = 3
    schedule_friday_block_after: str = "13:00"
    schedule_saturday_resume_at: str = "21:00"


settings = Settings()
