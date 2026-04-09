"""
Trinity — Metrics Module
Direct prometheus_client metrics for pipeline, incidents, and guardrails.
Exposes /metrics endpoint via make_asgi_app() or generate_latest().
"""

import time
import logging
from contextlib import contextmanager

from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    Info,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

logger = logging.getLogger("triageforge.observability.metrics")


# ============================================
# Counters
# ============================================

INCIDENTS_CREATED = Counter(
    "triageforge_incidents_created_total",
    "Total incidents submitted",
)

INCIDENTS_BY_SEVERITY = Counter(
    "triageforge_incidents_by_severity_total",
    "Incidents broken down by final severity",
    ["severity"],
)

PIPELINE_RUNS = Counter(
    "triageforge_pipeline_runs_total",
    "Total triage pipeline executions",
    ["status"],  # completed, error
)

GUARDRAILS_TRIGGERED = Counter(
    "triageforge_guardrails_triggered_total",
    "Guardrail activations by type",
    ["guardrail_type"],  # injection, pii, validation
)

NOTIFICATIONS_SENT = Counter(
    "triageforge_notifications_sent_total",
    "Notifications dispatched by channel",
    ["channel"],  # slack, email
)

TICKETS_CREATED = Counter(
    "triageforge_tickets_created_total",
    "Tickets created in external systems",
)

INCIDENTS_RESOLVED = Counter(
    "triageforge_incidents_resolved_total",
    "Incidents resolved",
)


# ============================================
# Histograms
# ============================================

PIPELINE_DURATION = Histogram(
    "triageforge_pipeline_duration_seconds",
    "End-to-end triage pipeline execution time",
    buckets=[1, 2, 5, 10, 15, 20, 30, 45, 60, 90, 120],
)

STAGE_DURATION = Histogram(
    "triageforge_pipeline_stage_duration_seconds",
    "Per-agent stage execution time",
    ["stage"],  # intake, code_analysis, doc_analysis, dedup, router, persist
    buckets=[0.5, 1, 2, 3, 5, 10, 15, 20, 30],
)


# ============================================
# Gauges
# ============================================

ACTIVE_PIPELINES = Gauge(
    "triageforge_active_pipelines",
    "Number of pipelines currently executing",
)


# ============================================
# Info
# ============================================

APP_INFO = Info(
    "triageforge",
    "Trinity application metadata",
)
APP_INFO.info({
    "version": "1.0.0",
    "service": "triageforge-backend",
})


# ============================================
# Helper: Stage Timer Context Manager
# ============================================

@contextmanager
def stage_timer(stage_name: str):
    """
    Context manager that records the duration of a pipeline stage.
    
    Usage:
        with stage_timer("intake"):
            await run_intake(state)
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        STAGE_DURATION.labels(stage=stage_name).observe(elapsed)
        logger.debug("Stage %s completed in %.2fs", stage_name, elapsed)


@contextmanager
def pipeline_timer():
    """
    Context manager that records the total pipeline execution time.
    
    Usage:
        with pipeline_timer():
            final_state = await graph.ainvoke(initial_state)
    """
    ACTIVE_PIPELINES.inc()
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        PIPELINE_DURATION.observe(elapsed)
        ACTIVE_PIPELINES.dec()
        logger.debug("Pipeline completed in %.2fs", elapsed)


def get_metrics_response():
    """Generate Prometheus metrics text for the /metrics endpoint."""
    return generate_latest(), CONTENT_TYPE_LATEST
