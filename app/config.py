from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./holter.db"
    secret_key: str = "dev-only-change-me"
    access_token_minutes: int = 60 * 8
    admin_email: str = ""
    admin_password: str = ""


settings = Settings()
