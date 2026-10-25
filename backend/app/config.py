from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    environment: str = "development"  # development | production
    database_url: str = "sqlite:///./ontoact.db"
    # Signs data-plane payloads and query cursors.
    secret_key: str = ""
    # There is no sign-in: every request acts as this built-in user.
    workspace_user: str = "planner"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # Host tests use 127.0.0.1:6381; Docker Compose uses falkordb:6379.
    falkordb_host: str = "falkordb"
    falkordb_port: int = 6379

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

# Production refuses to start without a signing key.
if settings.environment == "production" and not settings.secret_key:
    raise RuntimeError("ENVIRONMENT=production requires SECRET_KEY")
