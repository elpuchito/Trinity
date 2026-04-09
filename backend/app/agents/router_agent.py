"""
TriageForge — Router Agent
Final decision-maker: synthesizes all sub-agent outputs, assigns final
severity, determines team routing, and plans notifications.
"""

import json
import logging

import google.generativeai as genai

from app.config import get_settings

logger = logging.getLogger("triageforge.agents.router")

# Team routing based on affected service
TEAM_ROUTING = {
    "checkout": "platform-payments",
    "payment": "platform-payments",
    "order": "order-fulfillment",
    "product": "catalog-team",
    "graphql": "api-platform",
    "infrastructure": "sre-infra",
    "unknown": "sre-oncall",
}

# Notification strategy per severity
NOTIFICATION_STRATEGY = {
    "P1": {
        "channels": ["slack", "email"],
        "slack_channel": "#critical-incidents",
        "email_recipients": ["oncall@saleor-demo.com", "sre-leads@saleor-demo.com"],
        "urgency": "immediate",
    },
    "P2": {
        "channels": ["slack", "email"],
        "slack_channel": "#incidents",
        "email_recipients": ["oncall@saleor-demo.com"],
        "urgency": "high",
    },
    "P3": {
        "channels": ["slack"],
        "slack_channel": "#incidents",
        "email_recipients": [],
        "urgency": "normal",
    },
    "P4": {
        "channels": [],
        "slack_channel": "#low-priority",
        "email_recipients": [],
        "urgency": "low",
    },
}

ROUTER_PROMPT = """You are the final routing decision-maker for an SRE incident triage pipeline.

Given all the analysis from previous agents, make the final determination:

1. **Final severity** (P1-P4): Use ALL the evidence — intake severity hint, code analysis confidence, doc matches, duplicate status
2. **Triage summary**: A concise, actionable summary for the oncall engineer
3. **Recommended actions**: Top 3 immediate actions to take

Analysis from previous agents:

INTAKE:
- Affected Service: {affected_service}
- Error Type: {error_type}
- Severity Hint: {severity_hint}
- Error Codes: {error_codes}

CODE ANALYSIS:
- Root Cause Hypothesis: {code_root_cause}
- Confidence: {code_confidence}
- Related Files: {related_code_files}

DOC ANALYSIS:
- Suggested Runbook: {suggested_runbook}
- Known Issues: {known_issues}

DEDUP:
- Is Duplicate: {is_duplicate}
- Related Incidents: {related_incidents}

Respond with ONLY a valid JSON object:
{{
    "final_severity": "P1",
    "triage_summary": "Concise, actionable summary...",
    "recommended_actions": ["Action 1", "Action 2", "Action 3"],
    "routing_rationale": "Why this severity and team assignment"
}}"""


def _get_model():
    settings = get_settings()
    genai.configure(api_key=settings.google_api_key)
    return genai.GenerativeModel("gemini-3.1-flash-lite-preview")


async def run_router(state: dict) -> dict:
    """
    Make final routing decisions based on all agent outputs.
    """
    logger.info("🎯 Router Agent: Making final routing decision...")
    
    affected_service = state.get("affected_service", "unknown")
    
    # Determine team assignment
    assigned_team = TEAM_ROUTING.get(affected_service, "sre-oncall")
    
    # --- Call Gemini for final severity assessment ---
    prompt = ROUTER_PROMPT.format(
        affected_service=affected_service,
        error_type=state.get("error_type", "unknown"),
        severity_hint=state.get("severity_hint", "P3"),
        error_codes=", ".join(state.get("extracted_error_codes", [])) or "none",
        code_root_cause=state.get("code_root_cause", "not analyzed"),
        code_confidence=state.get("code_confidence", 0.0),
        related_code_files=", ".join(state.get("related_code_files", [])) or "none",
        suggested_runbook=state.get("suggested_runbook", "none")[:500],
        known_issues=", ".join(state.get("known_issues", [])) or "none",
        is_duplicate=state.get("is_duplicate", False),
        related_incidents=json.dumps(state.get("related_incidents", []))[:300],
    )
    
    try:
        model = _get_model()
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.1,
                max_output_tokens=1024,
                response_mime_type="application/json",
            ),
        )
        
        result = json.loads(response.text.strip())
        final_severity = result.get("final_severity", state.get("severity_hint", "P3"))
        triage_summary = result.get("triage_summary", "")
        recommended_actions = result.get("recommended_actions", [])
        routing_rationale = result.get("routing_rationale", "")
        
    except Exception as e:
        logger.error("Router LLM call failed: %s", e)
        # Fallback: use intake severity hint
        final_severity = state.get("severity_hint", "P3")
        triage_summary = (
            f"Incident affecting {affected_service} service. "
            f"Error type: {state.get('error_type', 'unknown')}. "
            f"Root cause hypothesis: {state.get('code_root_cause', 'not analyzed')[:200]}"
        )
        recommended_actions = [
            f"Check {affected_service} service logs",
            "Review the suggested runbook steps",
            "Verify if this is a known issue",
        ]
        routing_rationale = "Based on intake agent severity hint (LLM unavailable)."
    
    # Build notification plan
    notification_config = NOTIFICATION_STRATEGY.get(final_severity, NOTIFICATION_STRATEGY["P3"])
    notification_plan = []
    
    if "slack" in notification_config["channels"]:
        notification_plan.append({
            "channel": "slack",
            "recipient": notification_config["slack_channel"],
            "urgency": notification_config["urgency"],
        })
    
    for email in notification_config.get("email_recipients", []):
        notification_plan.append({
            "channel": "email",
            "recipient": email,
            "urgency": notification_config["urgency"],
        })
    
    # Always notify the reporter
    reporter_email = state.get("reporter_email", "")
    if reporter_email:
        notification_plan.append({
            "channel": "email",
            "recipient": reporter_email,
            "urgency": "confirmation",
        })
    
    # --- Update state ---
    state["final_severity"] = final_severity
    state["assigned_team"] = assigned_team
    state["notification_plan"] = notification_plan
    state["triage_summary"] = triage_summary
    state["recommended_actions"] = recommended_actions
    state["routing_rationale"] = routing_rationale
    
    logger.info(
        "✅ Router Agent: severity=%s, team=%s, notifications=%d",
        final_severity, assigned_team, len(notification_plan),
    )
    
    return state
