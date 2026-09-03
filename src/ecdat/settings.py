from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ECDAT_", env_file=".env", extra="ignore")

    env: str = "development"
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    postgres_dsn: str = "postgresql+psycopg://ecdat:ecdat@localhost:5432/ecdat"
    redis_url: str = "redis://localhost:6379/0"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "ecdat-development"
    quantum_horizon_years: float = 15.0
    allowed_scan_roots: str = "/workspace,/tmp,/var/lib/ecdat/intake"
    intake_dir: str = "/var/lib/ecdat/intake"
    max_upload_bytes: int = 512 * 1024 * 1024
    max_archive_members: int = 20_000
    max_extracted_bytes: int = 1024 * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
