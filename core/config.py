from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    POSTGRESQL_USERNAME: str
    POSTGRESQL_PASSWORD: str
    POSTGRESQL_SERVER: str
    POSTGRESQL_PORT: str
    POSTGRESQL_DATABASE: str
    PROJECT_NAME:str = "CloudForge default"
    
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int

    @property
    def SQLALCHEMY_DATABASE_URL(self) -> str:
        return f"postgresql://{self.POSTGRESQL_USERNAME}:{self.POSTGRESQL_PASSWORD}@{self.POSTGRESQL_SERVER}:{self.POSTGRESQL_PORT}/{self.POSTGRESQL_DATABASE}?client_encoding=utf8"
    
    
    model_config = SettingsConfigDict(
        env_file = ".env",
        env_file_encoding = "utf-8"
    )

settings = Settings()