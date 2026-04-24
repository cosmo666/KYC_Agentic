from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # App database
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    # Ollama + models
    ollama_base_url: str = "http://host.docker.internal:11434"
    chat_model: str = "gemma4:31b-cloud"
    ocr_model: str = "ministral-3:8b-cloud"
    embed_model: str = "bge-m3:latest"

    # Qdrant
    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection: str = "kyc_corpus"

    # Langfuse
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://langfuse:3000"

    # ipwhois
    ipwhois_api_key: str = ""

    # Upload dir (inside container)
    upload_dir: str = "/data/uploads"

    @property
    def db_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def db_url_sync(self) -> str:
        """Alembic uses the sync driver (psycopg)."""
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
