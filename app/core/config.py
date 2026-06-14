import os
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str

    # Auth
    secret_key: str                        # used for session signing — set a long random string
    session_expire_minutes: int = 60 * 8  # 8 hour sessions

    # App
    app_name: str = "Competitive Intelligence"
    debug: bool = False

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra  = "ignore"



@lru_cache()
def get_settings() -> Settings:
    return Settings()

