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


settings = Settings()
