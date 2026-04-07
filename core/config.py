from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    POSTGRESQL_USERNAME: str
    POSTGRESQL_PASSWORD: str
    POSTGRESQL_SERVER: str
    POSTGRESQL_PORT: str
    POSTGRESQL_DATABASE: str
    PROJECT_NAME:str = "CloudForge default"


    @property
    def SQLALCHEMY_DATABASE_URL(self) -> str:
        return f"postgresql://{self.POSTGRESQL_USERNAME}:{self.POSTGRESQL_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRESQL_PORT}/{self.POSTGRESQL_DATABASE}"
    

    class Config:
        env_file = "../.env"

settings = Settings()