import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PORT: int = 8000
    ENVIRONMENT: str = "development"
    FRONTEND_URL: str = "http://localhost:5173"
    WS_HEARTBEAT_INTERVAL: int = 30
    
    # Credentials (will load from environment, defaults to empty strings to avoid crashes)
    SARVAM_API_KEY: str = ""
    SARVAM_API_KEY_FALLBACK: str = ""
    SARVAM_API_KEY_FALLBACK_2: str = ""
    SARVAM_API_KEY_FALLBACK_3: str = ""
    SARVAM_API_KEY_FALLBACK_4: str = ""
    SARVAM_API_KEY_FALLBACK_5: str = ""
    SARVAM_API_KEY_FALLBACK_6: str = ""
    GEMINI_API_KEY: str = ""
    GEMINI_API_KEY_FALLBACK: str = ""
    GEMINI_API_KEY_FALLBACK_2: str = ""
    GEMINI_MODEL: str = "gemini-flash-lite-latest"
    
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_KEY: str = ""
    
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
