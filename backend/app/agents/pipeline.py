"""
TriageForge — LangGraph Pipeline Orchestration
Wires all agents into a stateful multi-agent pipeline using LangGraph.

Flow: Intake → [Code Analysis, Doc Analysis, Dedup] (parallel fan-out) → Router → Persist
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import TypedDict, Optional, Annotated

from langgraph.graph import StateGraph, END

from app.agents.intake_agent import run_intake
from app.agents.code_analyzer import run_code_analysis
from app.agents.doc_analyzer import run_doc_analysis
from app.agents.dedup_agent import run_dedup
from app.agents.router_agent import run_router

logger = logging.getLogger("triageforge.agents.pipeline")


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
# Node Wrapper Functions
# ============================================

def _add_stage_update(state: dict, stage: str, status: str, message: str = "") -> dict:
    """Add a pipeline stage update for WebSocket broadcasting."""
    if "pipeline_stages" not in state:
        state["pipeline_stages"] = []
    
    state["pipeline_stages"].append({
        "stage": stage,
        "status": status,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    return state


async def intake_node(state: dict) -> dict:
    """Intake agent node — extract structured data from raw input."""
    state = _add_stage_update(state, "intake", "running", "Analyzing incident report...")
    try:
        state = await run_intake(state)
        state = _add_stage_update(state, "intake", "completed",
                                   f"Service: {state.get('affected_service', 'unknown')}, "
                                   f"Severity hint: {state.get('severity_hint', '?')}")
    except Exception as e:
        logger.error("Intake agent failed: %s", e)
        state["errors"] = state.get("errors", []) + [f"intake: {str(e)}"]
        state = _add_stage_update(state, "intake", "error", str(e))
    return state


async def code_analysis_node(state: dict) -> dict:
    """Code analyzer node — RAG search over Saleor codebase."""
    state = _add_stage_update(state, "code_analysis", "running", "Searching codebase...")
    try:
        state = await run_code_analysis(state)
        state = _add_stage_update(state, "code_analysis", "completed",
                                   f"Found {len(state.get('related_code_files', []))} relevant files")
    except Exception as e:
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
    try:
        state = await run_doc_analysis(state)
        state = _add_stage_update(state, "doc_analysis", "completed",
                                   f"Found {len(state.get('known_issues', []))} known issues")
    except Exception as e:
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
    try:
        state = await run_dedup(state)
        dup_msg = "Duplicate found!" if state.get("is_duplicate") else "No duplicates"
        state = _add_stage_update(state, "dedup", "completed", dup_msg)
    except Exception as e:
        logger.error("Dedup agent failed: %s", e)
        state["errors"] = state.get("errors", []) + [f"dedup: {str(e)}"]
        state = _add_stage_update(state, "dedup", "error", str(e))
        state.setdefault("is_duplicate", False)
        state.setdefault("duplicate_of_id", None)
    return state


async def router_node(state: dict) -> dict:
    """Router agent node — final severity and team assignment."""
    state = _add_stage_update(state, "router", "running", "Making routing decision...")
    try:
        state = await run_router(state)
        state = _add_stage_update(state, "router", "completed",
                                   f"Severity: {state.get('final_severity', '?')}, "
                                   f"Team: {state.get('assigned_team', '?')}")
    except Exception as e:
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
        
    Returns:
        Final pipeline state with all agent outputs
    """
    logger.info("🚀 Starting triage pipeline for incident %s", incident_id)
    
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
        # Run the graph
        final_state = await graph.ainvoke(initial_state)
        
        logger.info(
            "✅ Pipeline complete for %s: severity=%s, team=%s, stages=%d",
            incident_id,
            final_state.get("final_severity", "?"),
            final_state.get("assigned_team", "?"),
            len(final_state.get("pipeline_stages", [])),
        )
        
        return final_state
        
    except Exception as e:
        logger.error("Pipeline execution failed for %s: %s", incident_id, e)
        initial_state["errors"].append(f"pipeline: {str(e)}")
        initial_state["pipeline_end_time"] = datetime.now(timezone.utc).isoformat()
        return initial_state
