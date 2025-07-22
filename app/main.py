from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.api.v1.endpoints import router as v1_router
from app.config import settings
from app.database.database import init_db

# Create rate limiter
limiter = Limiter(key_func=get_remote_address)

# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    description="Finance Assistant with Xero API Integration",
    version="1.0.0",
    debug=settings.debug
)

# Add rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,  # Configure this properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    init_db()
    print("✅ Database initialized successfully")


@app.get("/debug")
async def debug_config():
    """Debug endpoint to check environment variables"""
    return {
        "client_id": settings.xero_client_id[:10] + "..." if settings.xero_client_id else "NOT_SET",
        "client_secret": "SET" if settings.xero_client_secret else "NOT_SET",
        "redirect_uri": settings.xero_redirect_uri,
        "auth_url": settings.xero_auth_url,
        "token_url": settings.xero_token_url,
        "scope": settings.xero_scope
    }


@app.get("/")
@limiter.limit("10/minute")
async def root(request: Request):
    """Root endpoint with basic information"""
    return {
        "message": "Finance Assistant API",
        "version": "1.0.0",
        "docs": "/docs",
        "debug": "/debug",
        "auth_endpoints": {
            "login": "/api/v1/auth/login",
            "login_redirect": "/api/v1/auth/login/redirect",
            "callback": "/api/v1/auth/callback",
            "callback_html": "/api/v1/auth/callback/html"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


# Include v1uter (includes all v1 endpoints with API key auth)
app.include_router(v1_router, prefix="/api/v1")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug
    ) 