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
from app.api.tickets import router as tickets_router
from app.api.notifications import router as notifications_router
from app.observability.logging_config import setup_structured_logging
from app.observability.metrics import get_metrics_response

# ============================================
# Structured Logging (must be first)
# ============================================
setup_structured_logging()
logger = logging.getLogger("triageforge")

settings = get_settings()


# ============================================
# OpenTelemetry Setup
# ============================================
def setup_telemetry():
    """Initialize OpenTelemetry tracing with auto-instrumentors."""
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
        logger.info("OpenTelemetry exporting to %s", settings.otel_exporter_otlp_endpoint)
    except Exception as e:
        logger.warning("Failed to connect to OTel collector: %s. Traces will be local only.", e)

    trace.set_tracer_provider(provider)

    # Auto-instrument SQLAlchemy and Redis for deep trace visibility
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        SQLAlchemyInstrumentor().instrument()
        logger.info("SQLAlchemy auto-instrumentation enabled")
    except Exception as e:
        logger.warning("SQLAlchemy instrumentation failed: %s", e)

    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        RedisInstrumentor().instrument()
        logger.info("Redis auto-instrumentation enabled")
    except Exception as e:
        logger.warning("Redis instrumentation failed: %s", e)

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

    # Index e-commerce codebase into ChromaDB (skip if already indexed)
    try:
        from app.rag.indexer import index_all
        index_result = await index_all()
        code_status = index_result.get("code", {}).get("status", "unknown")
        docs_status = index_result.get("docs", {}).get("status", "unknown")
        logger.info(
            "🔍 RAG indexing: code=%s, docs=%s",
            code_status, docs_status,
        )
    except Exception as e:
        logger.warning("⚠️  RAG indexing failed (ChromaDB may not be ready): %s", e)

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
app.include_router(tickets_router)
app.include_router(notifications_router)


@app.get("/health", tags=["system"])
async def health_check():
    """Health check endpoint for Docker and monitoring."""
    return {
        "status": "healthy",
        "service": settings.app_name,
        "version": settings.app_version,
    }


@app.get("/metrics", tags=["system"], include_in_schema=False)
async def metrics_endpoint():
    """Prometheus metrics endpoint for scraping."""
    from fastapi.responses import Response
    body, content_type = get_metrics_response()
    return Response(content=body, media_type=content_type)


@app.get("/", tags=["system"])
async def root():
    """Root endpoint — API info."""
    return {
        "name": "TriageForge API",
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health",
    }
