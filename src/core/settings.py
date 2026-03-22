from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    MONGO_URI: str = "mongodb://root:example@localhost:27017"
    MONGO_DB: str = "memory"

    model_config = {"env_prefix": "MEMORY_"}


settings = Settings()
