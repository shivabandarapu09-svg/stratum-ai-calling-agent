import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import init_db
from app.api.auth import router as auth_router
from app.api.agents import router as agents_router
from app.api.calls import router as calls_router
from app.api.knowledge import router as knowledge_router
from app.api.campaigns import router as campaigns_router
from app.api.analytics import router as analytics_router
from app.api.telephony import router as telephony_router
from app.api.leads import router as leads_router
from app.api.ws_voice import router as ws_voice_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize DB and seeds
    print("[Stratum AI] Initializing enterprise database and loading 6 Human-Realism calling blueprints...")
    init_db()
    yield
    # Shutdown
    print("[Stratum AI] Server shutting down.")

app = FastAPI(
    title=settings.APP_NAME,
    description="Stratum AI — Hyper-Realistic Multilingual AI Calling Agent Platform synthesizing Sarvam AI, Vapi, Retell AI, Bolna, Trikon, and Outpero.",
    version="3.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG or settings.APP_ENV == "development" else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.DEBUG or settings.APP_ENV == "development" else None,
)

# CORS: only the configured dashboard origins may call the API from a browser (see CORS_ORIGINS).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Tenant-ID"],
)

# Mount API Routers
app.include_router(auth_router, prefix=settings.API_PREFIX)
app.include_router(agents_router, prefix=settings.API_PREFIX)
app.include_router(calls_router, prefix=settings.API_PREFIX)
app.include_router(knowledge_router, prefix=settings.API_PREFIX)
app.include_router(campaigns_router, prefix=settings.API_PREFIX)
app.include_router(analytics_router, prefix=settings.API_PREFIX)
app.include_router(telephony_router, prefix=settings.API_PREFIX)
app.include_router(leads_router, prefix=settings.API_PREFIX)
app.include_router(ws_voice_router)

@app.get("/")
def root():
    return {
        "status": "online",
        "service": settings.APP_NAME,
        "platform": "Stratum Enterprise AI",
    }

@app.get("/api/health")
def health_check():
    # Public liveness probe: deliberately exposes no provider or configuration details.
    return {"status": "healthy", "platform": "Stratum Enterprise AI"}
