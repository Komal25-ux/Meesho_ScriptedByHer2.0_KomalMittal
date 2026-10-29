import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PORT: int = 8000
    ENVIRONMENT: str = "development"
    FRONTEND_URL: str = "http://localhost:5173"
    # Browser origins allowed to call the API and open the trace socket,
    # comma-separated. FRONTEND_URL is always added to these.
    CORS_ORIGINS: str = "http://localhost:5173,https://meesho-sakhi-komal25.vercel.app"
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
    GEMINI_FALLBACK_MODELS: str = "gemini-3.5-flash-lite,gemini-2.5-flash,gemini-3.1-flash-lite,gemini-3-flash-preview"
    
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_KEY: str = ""

    # Where cross-turn conversation state lives (backend/core/session.py).
    # Empty means: the session_state table whenever Supabase is configured,
    # memory otherwise. Tests force "memory".
    SESSION_STORE: str = ""
    SESSION_TTL_HOURS: int = 24

    # Abuse limits (backend/api/limits.py). Per instance, per minute.
    RATE_LIMIT_IP_PER_MINUTE: int = 60
    RATE_LIMIT_SESSION_PER_MINUTE: int = 20
    # Whole request body. A minute-long voice note is well under 1 MB.
    MAX_REQUEST_BYTES: int = 6_000_000
    
    @property
    def allowed_origins(self) -> list[str]:
        origins = [o.strip().rstrip("/") for o in f"{self.CORS_ORIGINS},{self.FRONTEND_URL}".split(",")]
        return sorted({o for o in origins if o})

settings = Settings()
