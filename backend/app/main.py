"""
TriageForge — Main Application
FastAPI app with OpenTelemetry instrumentation, CORS, and lifecycle management.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from app.config import get_settings
from app.database import init_db, close_db
from app.api.incidents import router as incidents_router

# ============================================
# Logging
# ============================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("triageforge")

settings = get_settings()


# ============================================
# OpenTelemetry Setup
# ============================================
def setup_telemetry():
    """Initialize OpenTelemetry tracing."""
    resource = Resource.create({
        "service.name": settings.otel_service_name,
        "service.version": settings.app_version,
    })
    provider = TracerProvider(resource=resource)

    try:
        otlp_exporter = OTLPSpanExporter(
            endpoint=settings.otel_exporter_otlp_endpoint,
            insecure=True,
        )
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        logger.info(f"OpenTelemetry exporting to {settings.otel_exporter_otlp_endpoint}")
    except Exception as e:
        logger.warning(f"Failed to connect to OTel collector: {e}. Traces will be local only.")

    trace.set_tracer_provider(provider)
    return provider


# ============================================
# App Lifecycle
# ============================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle management."""
    logger.info("🚀 TriageForge starting up...")

    # Initialize OpenTelemetry
    setup_telemetry()
    logger.info("📡 OpenTelemetry initialized")

    # Initialize database
    await init_db()
    logger.info("🗄️  Database initialized")

    logger.info("✅ TriageForge is ready!")
    yield

    # Shutdown
    logger.info("🛑 TriageForge shutting down...")
    await close_db()
    logger.info("👋 Goodbye!")


# ============================================
# FastAPI App
# ============================================
app = FastAPI(
    title="TriageForge",
    description="SRE Incident Intake & Triage Agent — Intelligent incident triage with multimodal AI analysis",
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_url,
        "http://localhost:3000",
        "http://localhost:5173",
        "http://frontend:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OpenTelemetry auto-instrumentation
FastAPIInstrumentor.instrument_app(app)

# Mount uploads directory for serving attachments
import os
os.makedirs("/app/uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="/app/uploads"), name="uploads")

# ============================================
# Routes
# ============================================

# Include API routers
app.include_router(incidents_router)


@app.get("/health", tags=["system"])
async def health_check():
    """Health check endpoint for Docker and monitoring."""
    return {
        "status": "healthy",
        "service": settings.app_name,
        "version": settings.app_version,
    }


@app.get("/", tags=["system"])
async def root():
    """Root endpoint — API info."""
    return {
        "name": "TriageForge API",
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health",
    }
