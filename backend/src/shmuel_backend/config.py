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

    # Yad2 import egress proxy. Yad2 is behind ShieldSquare bot protection that
    # blocks datacenter IPs (Cloud Run). Point this at a residential proxy or a
    # scraping API (e.g. http://user:pass@host:port) to route the import fetch
    # through a trusted IP. Empty = fetch directly (works from residential IPs,
    # often blocked from cloud hosts).
    yad2_fetch_proxy: str = ""

    # whatsapp-daemon — self-hosted Baileys daemon in `whatsapp-daemon/`.
    # Empty URL = no-op (calls log "would have sent..." and return None).
    # Token is a shared secret; daemon must be configured with the same value.
    whatsapp_daemon_url: str = ""
    whatsapp_daemon_token: str = ""

    # Chatbot (Phase 3.1). The DB-backed `bot_config.chatbot_enabled` flag
    # gates whether replies actually go out; these env vars set model and
    # rate-limit knobs.
    openai_chat_model: str = "gpt-4o-mini"
    chatbot_min_reply_interval_seconds: int = 30
    chatbot_max_matches_per_reply: int = 3
    # Site URL the chatbot links each match to. Falls through to the
    # newsletter site URL when blank.
    chatbot_site_base_url: str = ""

    # Daily digest (Phase 3.2). Recipient for the 08:00 Jerusalem
    # rollup email of yesterday's summaries + open action items. Empty
    # disables the digest (the endpoint reports a skip reason).
    broker_email: str = ""
    # How many hours of summaries to include in each digest. 24 = the
    # full previous day; tune higher to catch slow-arriving messages.
    digest_window_hours: int = 24


settings = Settings()
