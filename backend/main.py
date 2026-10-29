import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.config import settings
from backend.api.chat_router import router as chat_router
from backend.api.ws_router import router as ws_router
from backend.db.supabase_client import db_client
from backend.api.limits import BodySizeLimit

# Initialize Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("sakhi-backend")

# Initialize FastAPI App
app = FastAPI(
    title="🌸 Sakhi API Gateway 🌸",
    description="The backend server for Sakhi - voice-native AI business co-pilot for Meesho resellers.",
    version="2.5"
)

# Only the deployed frontend and local dev may call the API from a browser.
# No cookies or auth headers are used, so credentials stay off.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    expose_headers=["Server-Timing", "Retry-After"],
)

# Added last so it runs first: an oversized body is refused before any
# other middleware or route touches it.
app.add_middleware(BodySizeLimit, max_bytes=settings.MAX_REQUEST_BYTES)

# Register routes
app.include_router(chat_router, prefix="/api/v1")
app.include_router(ws_router)

@app.get("/")
def read_root():
    return {
        "status": "online",
        "service": "Sakhi API Gateway",
        "version": "2.5",
        "docs": "/docs"
    }

@app.get("/health")
def health_check():
    supabase_status = "connected"
    if db_client.is_mock():
        supabase_status = "mock_mode"
        
    return {
        "status": "healthy",
        "supabase": supabase_status,
        "environment": settings.ENVIRONMENT
    }

if __name__ == "__main__":
    import uvicorn
    # Read port from configuration
    port = settings.PORT
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
