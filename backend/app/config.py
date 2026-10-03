from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str
    SUPABASE_URL: str
    SUPABASE_SERVICE_KEY: str
    SUPABASE_BUCKET: str = "audio"
    GNANI_API_KEY: str
    GNANI_BASE_URL: str = "https://api.vachana.ai"
    GEMINI_API_KEY: str
    GEMINI_MODEL: str = "gemini-2.5-flash"
    CORS_ORIGINS: str = "http://localhost:3000"
    MAX_UPLOAD_BYTES: int = 100 * 1024 * 1024  
    POLL_INTERVAL_SECONDS: int = 12
    JOB_TIMEOUT_SECONDS: int = 1800     
    STALE_HEARTBEAT_SECONDS: int = 300   

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

settings = Settings()
