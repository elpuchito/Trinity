"""
TriageForge — Structured Logging Configuration
JSON-formatted logs with OpenTelemetry trace correlation (trace_id, span_id).
Enables Loki → Tempo cross-linking in Grafana.
"""

import logging
import json
import sys
from datetime import datetime, timezone

from opentelemetry import trace


class StructuredJsonFormatter(logging.Formatter):
    """
    JSON log formatter that injects OTel trace context into every log record.
    
    Output format:
    {
        "timestamp": "2026-04-09T12:00:00.000Z",
        "level": "INFO",
        "logger": "triageforge.agents.pipeline",
        "message": "Pipeline complete for abc-123",
        "trace_id": "0af7651916cd43dd8448eb211c80319c",
        "span_id": "b7ad6b7169203331",
        "service": "triageforge-backend"
    }
    """

    def format(self, record: logging.LogRecord) -> str:
        # Get current span context for trace correlation
        span = trace.get_current_span()
        ctx = span.get_span_context() if span else None

        trace_id = ""
        span_id = ""
        if ctx and ctx.trace_id:
            trace_id = format(ctx.trace_id, '032x')
            span_id = format(ctx.span_id, '016x')

        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": "triageforge-backend",
        }

        # Only include trace fields if there's an active trace
        if trace_id:
            log_entry["trace_id"] = trace_id
            log_entry["span_id"] = span_id

        # Include exception info if present
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Include extra fields if provided
        for key in ("incident_id", "stage", "severity", "team"):
            if hasattr(record, key):
                log_entry[key] = getattr(record, key)

        return json.dumps(log_entry, default=str)


def setup_structured_logging(level: int = logging.INFO):
    """
    Replace the default logging configuration with structured JSON output.
    Call this BEFORE initializing OpenTelemetry (so early logs still use JSON format).
    """
    root_logger = logging.getLogger()

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create JSON handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredJsonFormatter())

    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    # Suppress noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("opentelemetry").setLevel(logging.WARNING)
    logging.getLogger("grpc").setLevel(logging.WARNING)

    logging.getLogger("triageforge").info("Structured JSON logging initialized")
