from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    environment: str = "development"  # development | production
    # JWT by default; compose opts into ``local_single_user`` explicitly so a plain
    # backend start never silently changes the security boundary.
    auth_mode: str = "jwt"  # local_single_user | jwt
    database_url: str = "sqlite:///./ontoact.db"
    secret_key: str = ""
    first_admin_user: str = "admin"
    first_admin_password: str = ""
    access_token_expire_minutes: int = 1440  # 24h
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # Host tests use 127.0.0.1:6381; Docker Compose uses falkordb:6379.
    falkordb_host: str = "falkordb"
    falkordb_port: int = 6379

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

# Production refuses to start with default credentials.
if settings.environment == "production":
    _insecure = [name for name, value in (("SECRET_KEY", settings.secret_key),
                                          ("FIRST_ADMIN_PASSWORD", settings.first_admin_password)) if not value]
    if _insecure:
        raise RuntimeError(f"ENVIRONMENT=production requires these settings: {', '.join(_insecure)}")
