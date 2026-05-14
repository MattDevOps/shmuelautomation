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

    # Resend transactional email. Empty = no-op (subscribe still records the
    # row, the email just doesn't go out — keeps local dev painless).
    resend_api_key: str = ""
    newsletter_from_email: str = "Classic Jerusalem Realty <newsletter@classicjerusalem.com>"
    # Public base URL the confirmation/unsubscribe links point at. The
    # backend itself sits behind the Worker; both layers serve /public/* so
    # this is the right host for the click-through links.
    newsletter_api_base_url: str = "http://localhost:8000"
    # Public site base URL — used in email bodies to link each property
    # back to Shmuel's WordPress site so clicks land on listings, not the API.
    newsletter_site_base_url: str = "https://classicjerusalem.com"
    # Send a digest once a subscriber has this many unseen matching properties.
    newsletter_digest_threshold: int = 3

    # OpenAI for content translation (properties / blog / neighborhoods into
    # ES, FR, HE). Empty = no-op (sync logs would-be calls, no Postgres writes).
    openai_api_key: str = ""
    openai_translate_model: str = "gpt-4o-mini"

    # WP REST base used by the translation sync service to source content.
    wp_rest_base: str = "https://realestateadmin2025.classicjerusalem.com/wp-json/wp/v2"


settings = Settings()
