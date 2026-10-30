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
    lifespan=lifespan
)

# Enable CORS for frontend dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
        "languages_supported": settings.SUPPORTED_LANGUAGES,
        "speed_to_lead_latency_target": "<5 seconds",
        "industry_blueprints": [
            "real_estate", "clinic_healthcare", "education_admissions",
            "ecommerce_cod", "b2b_saas_sdr", "bfsi_fintech"
        ]
    }

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "platform": "Stratum Enterprise AI",
        "llm_provider": settings.DEFAULT_LLM_PROVIDER,
        "stt_provider": settings.DEFAULT_STT_PROVIDER,
        "tts_provider": settings.DEFAULT_TTS_PROVIDER,
        "telephony": settings.TELEPHONY_PROVIDER,
        "speed_to_lead_auto_dial": settings.SPEED_TO_LEAD_AUTO_DIAL
    }
