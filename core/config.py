from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import List, Union

class Settings(BaseSettings):
    BOT_TOKEN: str
    API_ID: int
    API_HASH: str
    
    # Поддержка списка ID админов
    ADMIN_IDS: List[int]
    
    # Database
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str
    DB_HOST: str
    DB_PORT: int = 5432

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def parse_admin_ids(cls, v: Union[str, int, List[int]]) -> List[int]:
        if isinstance(v, int):
            return [v]
        if isinstance(v, str):
            # Убираем лишние символы и делим по запятой
            v = v.replace("[", "").replace("]", "").replace(" ", "")
            return [int(i) for i in v.split(",") if i]
        return v

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()