from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import List, Union, Any

class Settings(BaseSettings):
    BOT_TOKEN: str

    # Принимаем как Any, чтобы pydantic-settings не пытался принудительно парсить это как JSON-список
    ADMIN_IDS: Any
    
    # Database
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str
    DB_HOST: str
    DB_PORT: int = 5432

    DB_URL: str

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def parse_admin_ids(cls, v: Any) -> List[int]:
        if isinstance(v, int):
            return [v]
        if isinstance(v, str):
            # Если это строка (из .env), чистим и делим по запятой
            v = v.replace("[", "").replace("]", "").replace(" ", "")
            try:
                return [int(i) for i in v.split(",") if i]
            except ValueError:
                return []
        if isinstance(v, list):
            return [int(i) for i in v]
        return []

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()