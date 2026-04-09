"""
TriageForge — LangGraph Pipeline Orchestration
Wires all agents into a stateful multi-agent pipeline using LangGraph.

Flow: Intake → [Code Analysis, Doc Analysis, Dedup] (parallel fan-out) → Router → Persist
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import TypedDict, Optional, Annotated, Callable, Awaitable

from langgraph.graph import StateGraph, END

from app.agents.intake_agent import run_intake
from app.agents.code_analyzer import run_code_analysis
from app.agents.doc_analyzer import run_doc_analysis
from app.agents.dedup_agent import run_dedup
from app.agents.router_agent import run_router
from app.observability.tracing import get_tracer
from app.observability.metrics import (
    stage_timer, pipeline_timer,
    PIPELINE_RUNS, INCIDENTS_BY_SEVERITY,
)

logger = logging.getLogger("triageforge.agents.pipeline")
tracer = get_tracer("triageforge.pipeline")


# ============================================
# Pipeline State
# ============================================

class TriageState(TypedDict, total=False):
    """Full pipeline state shared across all agents."""
    
    # --- Incident Input ---
    incident_id: str
    raw_title: str
    raw_description: str
    reporter_name: str
    reporter_email: str
    attachments: list

    # --- Intake Agent Output ---
    structured_title: str
    structured_description: str
    affected_service: str
    error_type: str
    severity_hint: str
    extracted_error_codes: list
    extracted_stack_traces: list
    keywords: list
    visual_analysis: Optional[str]
    guardrails_triggered: list

    # --- Code Analyzer Output ---
    related_code_files: list
    code_root_cause: str
    code_confidence: float
    code_analysis_summary: str

    # --- Doc Analyzer Output ---
    suggested_runbook: str
    known_issues: list
    doc_references: list
    mitigation_summary: str
    estimated_resolution_time: str

    # --- Dedup Agent Output ---
    is_duplicate: bool
    duplicate_of_id: Optional[str]
    similarity_scores: list
    related_incidents: list

    # --- Router Agent Output ---
    final_severity: str
    assigned_team: str
    notification_plan: list
    triage_summary: str
    recommended_actions: list
    routing_rationale: str

    # --- Pipeline Metadata ---
    pipeline_stages: list
    errors: list
    pipeline_start_time: str
    pipeline_end_time: str


# ============================================
# Stage Broadcast Callback Type
# ============================================

# Callback signature: async fn(incident_id, stage_data) -> None
StageCallback = Callable[[str, dict], Awaitable[None]]

# Module-level callback holder (set per pipeline run)
_active_callback: Optional[StageCallback] = None
_active_incident_id: Optional[str] = None


# ============================================
# Node Wrapper Functions
# ============================================

def _add_stage_update(state: dict, stage: str, status: str, message: str = "") -> dict:
    """Add a pipeline stage update and broadcast via callback if available."""
    if "pipeline_stages" not in state:
        state["pipeline_stages"] = []
    
    stage_data = {
        "stage": stage,
        "status": status,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    state["pipeline_stages"].append(stage_data)
    
    # Fire real-time broadcast callback
    if _active_callback and _active_incident_id:
        try:
            asyncio.get_event_loop().create_task(
                _active_callback(_active_incident_id, {
                    "type": "stage_update",
                    "incident_id": _active_incident_id,
                    **stage_data,
                })
            )
        except Exception:
            pass  # Never let callback errors break the pipeline
    
    return state


async def intake_node(state: dict) -> dict:
    """Intake agent node — extract structured data from raw input."""
    state = _add_stage_update(state, "intake", "running", "Analyzing incident report...")
    with tracer.start_as_current_span("pipeline.intake") as span:
        span.set_attribute("incident.id", state.get("incident_id", ""))
        with stage_timer("intake"):
            try:
                state = await run_intake(state)
                span.set_attribute("intake.service", state.get("affected_service", ""))
                span.set_attribute("intake.severity_hint", state.get("severity_hint", ""))
                state = _add_stage_update(state, "intake", "completed",
                                           f"Service: {state.get('affected_service', 'unknown')}, "
                                           f"Severity hint: {state.get('severity_hint', '?')}")
            except Exception as e:
                span.set_attribute("error", True)
                span.set_attribute("error.message", str(e))
                logger.error("Intake agent failed: %s", e)
                state["errors"] = state.get("errors", []) + [f"intake: {str(e)}"]
                state = _add_stage_update(state, "intake", "error", str(e))
    return state


async def code_analysis_node(state: dict) -> dict:
    """Code analyzer node — RAG search over Saleor codebase."""
    state = _add_stage_update(state, "code_analysis", "running", "Searching codebase...")
    with tracer.start_as_current_span("pipeline.code_analysis") as span:
        span.set_attribute("incident.id", state.get("incident_id", ""))
        with stage_timer("code_analysis"):
            try:
                state = await run_code_analysis(state)
                span.set_attribute("code.files_found", len(state.get("related_code_files", [])))
                span.set_attribute("code.confidence", state.get("code_confidence", 0.0))
                state = _add_stage_update(state, "code_analysis", "completed",
                                           f"Found {len(state.get('related_code_files', []))} relevant files")
            except Exception as e:
                span.set_attribute("error", True)
                span.set_attribute("error.message", str(e))
                logger.error("Code analysis agent failed: %s", e)
                state["errors"] = state.get("errors", []) + [f"code_analysis: {str(e)}"]
                state = _add_stage_update(state, "code_analysis", "error", str(e))
                state.setdefault("related_code_files", [])
                state.setdefault("code_root_cause", "Analysis failed")
                state.setdefault("code_confidence", 0.0)
    return state


async def doc_analysis_node(state: dict) -> dict:
    """Doc analyzer node — RAG search over documentation."""
    state = _add_stage_update(state, "doc_analysis", "running", "Searching documentation...")
    with tracer.start_as_current_span("pipeline.doc_analysis") as span:
        span.set_attribute("incident.id", state.get("incident_id", ""))
        with stage_timer("doc_analysis"):
            try:
                state = await run_doc_analysis(state)
                span.set_attribute("doc.known_issues", len(state.get("known_issues", [])))
                span.set_attribute("doc.references", len(state.get("doc_references", [])))
                state = _add_stage_update(state, "doc_analysis", "completed",
                                           f"Found {len(state.get('known_issues', []))} known issues")
            except Exception as e:
                span.set_attribute("error", True)
                span.set_attribute("error.message", str(e))
                logger.error("Doc analysis agent failed: %s", e)
                state["errors"] = state.get("errors", []) + [f"doc_analysis: {str(e)}"]
                state = _add_stage_update(state, "doc_analysis", "error", str(e))
                state.setdefault("suggested_runbook", "Not available")
                state.setdefault("known_issues", [])
                state.setdefault("doc_references", [])
    return state


async def dedup_node(state: dict) -> dict:
    """Dedup agent node — check for duplicate incidents."""
    state = _add_stage_update(state, "dedup", "running", "Checking for duplicates...")
    with tracer.start_as_current_span("pipeline.dedup") as span:
        span.set_attribute("incident.id", state.get("incident_id", ""))
        with stage_timer("dedup"):
            try:
                state = await run_dedup(state)
                span.set_attribute("dedup.is_duplicate", state.get("is_duplicate", False))
                span.set_attribute("dedup.similar_count", len(state.get("related_incidents", [])))
                dup_msg = "Duplicate found!" if state.get("is_duplicate") else "No duplicates"
                state = _add_stage_update(state, "dedup", "completed", dup_msg)
            except Exception as e:
                span.set_attribute("error", True)
                span.set_attribute("error.message", str(e))
                logger.error("Dedup agent failed: %s", e)
                state["errors"] = state.get("errors", []) + [f"dedup: {str(e)}"]
                state = _add_stage_update(state, "dedup", "error", str(e))
                state.setdefault("is_duplicate", False)
                state.setdefault("duplicate_of_id", None)
    return state


async def router_node(state: dict) -> dict:
    """Router agent node — final severity and team assignment."""
    state = _add_stage_update(state, "router", "running", "Making routing decision...")
    with tracer.start_as_current_span("pipeline.router") as span:
        span.set_attribute("incident.id", state.get("incident_id", ""))
        with stage_timer("router"):
            try:
                state = await run_router(state)
                span.set_attribute("router.severity", state.get("final_severity", ""))
                span.set_attribute("router.team", state.get("assigned_team", ""))
                state = _add_stage_update(state, "router", "completed",
                                           f"Severity: {state.get('final_severity', '?')}, "
                                           f"Team: {state.get('assigned_team', '?')}")
            except Exception as e:
                span.set_attribute("error", True)
                span.set_attribute("error.message", str(e))
                logger.error("Router agent failed: %s", e)
                state["errors"] = state.get("errors", []) + [f"router: {str(e)}"]
                state = _add_stage_update(state, "router", "error", str(e))
                state.setdefault("final_severity", state.get("severity_hint", "P3"))
                state.setdefault("assigned_team", "sre-oncall")
    return state


async def persist_node(state: dict) -> dict:
    """
    Persist triage results to the database.
    This is handled separately by the pipeline runner (trigger_triage_pipeline),
    so this node just marks completion.
    """
    with tracer.start_as_current_span("pipeline.persist") as span:
        span.set_attribute("incident.id", state.get("incident_id", ""))
        with stage_timer("persist"):
            state["pipeline_end_time"] = datetime.now(timezone.utc).isoformat()
            state = _add_stage_update(state, "persist", "completed", "Results saved to database")
            logger.info("📝 Pipeline complete — results ready for persistence")
    return state


# ============================================
# Build the LangGraph Pipeline
# ============================================

def build_triage_graph():
    """
    Build and compile the triage pipeline graph.
    
    Flow (sequential):
        intake → code_analysis → doc_analysis → dedup → router → persist → END
    
    Sequential avoids LangGraph's INVALID_CONCURRENT_GRAPH_UPDATE error
    that occurs when parallel nodes write to shared state keys (pipeline_stages, errors).
    The ~2s extra latency is irrelevant for a demo pipeline.
    """
    graph = StateGraph(TriageState)

    # Add nodes
    graph.add_node("intake", intake_node)
    graph.add_node("code_analysis", code_analysis_node)
    graph.add_node("doc_analysis", doc_analysis_node)
    graph.add_node("dedup", dedup_node)
    graph.add_node("router", router_node)
    graph.add_node("persist", persist_node)

    # Sequential chain
    graph.set_entry_point("intake")
    graph.add_edge("intake", "code_analysis")
    graph.add_edge("code_analysis", "doc_analysis")
    graph.add_edge("doc_analysis", "dedup")
    graph.add_edge("dedup", "router")
    graph.add_edge("router", "persist")
    graph.add_edge("persist", END)

    return graph.compile()


# Compiled graph singleton
_triage_graph = None


def get_triage_graph():
    """Get or create the compiled triage graph."""
    global _triage_graph
    if _triage_graph is None:
        _triage_graph = build_triage_graph()
    return _triage_graph


async def run_triage_pipeline(
    incident_id: str,
    title: str,
    description: str,
    reporter_name: str = "",
    reporter_email: str = "",
    attachments: list = None,
    stage_callback: Optional[StageCallback] = None,
) -> dict:
    """
    Run the full triage pipeline for an incident.
    
    Args:
        incident_id: UUID of the incident
        title: Incident title
        description: Incident description
        reporter_name: Name of the reporter
        reporter_email: Email of the reporter
        attachments: List of attachment metadata dicts
        stage_callback: Optional async callback for real-time stage broadcasts.
                        Signature: async fn(incident_id: str, stage_data: dict) -> None
        
    Returns:
        Final pipeline state with all agent outputs
    """
    global _active_callback, _active_incident_id
    
    logger.info("🚀 Starting triage pipeline for incident %s", incident_id)
    
    # Set module-level callback for node wrappers to use
    _active_callback = stage_callback
    _active_incident_id = incident_id
    
    initial_state = {
        "incident_id": incident_id,
        "raw_title": title,
        "raw_description": description,
        "reporter_name": reporter_name,
        "reporter_email": reporter_email,
        "attachments": attachments or [],
        "pipeline_stages": [],
        "errors": [],
        "pipeline_start_time": datetime.now(timezone.utc).isoformat(),
    }
    
    graph = get_triage_graph()
    
    try:
        # Run the graph with pipeline-level metrics
        with pipeline_timer():
            with tracer.start_as_current_span("pipeline.full_run") as span:
                span.set_attribute("incident.id", incident_id)
                span.set_attribute("incident.title", title[:100])
                final_state = await graph.ainvoke(initial_state)
                span.set_attribute("pipeline.severity", final_state.get("final_severity", ""))
                span.set_attribute("pipeline.team", final_state.get("assigned_team", ""))
                span.set_attribute("pipeline.stages", len(final_state.get("pipeline_stages", [])))
                span.set_attribute("pipeline.errors", len(final_state.get("errors", [])))
        
        # Record metrics
        PIPELINE_RUNS.labels(status="completed").inc()
        final_sev = final_state.get("final_severity", "UNKNOWN")
        INCIDENTS_BY_SEVERITY.labels(severity=final_sev).inc()
        
        logger.info(
            "✅ Pipeline complete for %s: severity=%s, team=%s, stages=%d",
            incident_id,
            final_state.get("final_severity", "?"),
            final_state.get("assigned_team", "?"),
            len(final_state.get("pipeline_stages", [])),
        )
        
        return final_state
        
    except Exception as e:
        PIPELINE_RUNS.labels(status="error").inc()
        logger.error("Pipeline execution failed for %s: %s", incident_id, e)
        initial_state["errors"].append(f"pipeline: {str(e)}")
        initial_state["pipeline_end_time"] = datetime.now(timezone.utc).isoformat()
        return initial_state
    finally:
        # Clean up module-level callback
        _active_callback = None
        _active_incident_id = None
