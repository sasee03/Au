from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    PORT: int = 4000

    # Single AURUM database — bronze/silver/gold are schemas inside it
    AURUM_DB_HOST: str = "localhost"
    AURUM_DB_PORT: int = 5432
    AURUM_DB_NAME: str = "aurum"          # one DB, three schemas
    AURUM_DB_USER: str = "postgres"
    AURUM_DB_PASSWORD: str = "postgres"

    # AI
    AI_PROVIDER: str = "ollama"   # "gemini" or "ollama"
    AI_ENDPOINT: str = "http://localhost:11434/api/generate"
    AI_MODEL: str = "llama3"
    AI_API_KEY: str = ""

    # Storage
    UPLOAD_DIR: str = "./uploads"

    # CORS
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    @property
    def aurum_dsn(self) -> str:
        return (
            f"postgresql://{self.AURUM_DB_USER}:{self.AURUM_DB_PASSWORD}"
            f"@{self.AURUM_DB_HOST}:{self.AURUM_DB_PORT}/{self.AURUM_DB_NAME}"
        )

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
