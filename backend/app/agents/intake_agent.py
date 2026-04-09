"""
Trinity — Intake Agent
First agent in the pipeline. Accepts raw incident data and produces
structured, enriched output using Gemini's multimodal capabilities.
"""

import os
import base64
import json
import logging
from typing import Optional

import google.generativeai as genai

from app.config import get_settings
from app.guardrails.injection_detector import detect_prompt_injection, sanitize_for_llm
from app.guardrails.pii_scrubber import scrub_pii
from app.guardrails.input_validator import is_image_file

logger = logging.getLogger("triageforge.agents.intake")

INTAKE_SYSTEM_PROMPT = """You are an expert SRE intake agent for an e-commerce platform built with Saleor (Python/Django).
Your job is to analyze incoming incident reports and extract structured triage information.

Given an incident report (text description and optionally a screenshot), extract:

1. **structured_title**: A clear, concise title (max 100 chars)
2. **structured_description**: A normalized, technical description
3. **affected_service**: One of: "checkout", "payment", "order", "product", "graphql", "infrastructure", "unknown"
4. **error_type**: One of: "500_error", "timeout", "data_corruption", "stock_error", "payment_error", "graphql_error", "performance", "ui_error", "authentication", "unknown"
5. **severity_hint**: Initial severity estimate: "P1", "P2", "P3", or "P4"
   - P1: Complete service outage or data loss affecting all users
   - P2: Major feature broken affecting many users
   - P3: Minor feature issue affecting some users
   - P4: Cosmetic or low-impact issue
6. **extracted_error_codes**: List of any error codes found (e.g., "INSUFFICIENT_STOCK", "HTTP 500")
7. **extracted_stack_traces**: List of any stack trace fragments found
8. **keywords**: 5-10 keywords for searching the codebase (e.g., ["checkout", "total_gross_amount", "TypeError", "None"])

Respond ONLY with a valid JSON object. No markdown, no explanation."""

IMAGE_ANALYSIS_PROMPT = """Additionally, analyze this screenshot from the incident.
Extract any visible:
- Error codes or HTTP status codes
- Stack traces or error messages
- UI state (which page, what's broken)
- Browser console errors if visible

Incorporate your findings into the structured fields above."""


def _get_model():
    """Initialize the Gemini model."""
    settings = get_settings()
    genai.configure(api_key=settings.google_api_key)
    return genai.GenerativeModel("gemini-3.1-flash-lite-preview")


async def run_intake(state: dict) -> dict:
    """
    Run the intake agent to extract structured data from raw incident input.
    
    Input state keys:
        - raw_title: str
        - raw_description: str  
        - attachments: list[dict] (file metadata with 'path' and 'content_type')
    
    Output: Updated state with structured fields.
    """
    logger.info("🔍 Intake Agent: Processing incident...")
    
    raw_title = state.get("raw_title", "")
    raw_description = state.get("raw_description", "")
    attachments = state.get("attachments", [])
    
    # --- Guardrails ---
    
    # 1. Prompt injection detection
    combined_text = f"{raw_title}\n{raw_description}"
    is_injection, injection_details = detect_prompt_injection(combined_text)
    if is_injection:
        logger.warning("⚠️ Prompt injection detected in incident input: %s", injection_details)
        state["guardrails_triggered"] = state.get("guardrails_triggered", [])
        state["guardrails_triggered"].append({
            "type": "prompt_injection",
            "details": injection_details,
        })
    
    # 2. PII scrubbing
    scrubbed_description, pii_detections = scrub_pii(raw_description)
    scrubbed_title, title_pii = scrub_pii(raw_title)
    if pii_detections or title_pii:
        state["guardrails_triggered"] = state.get("guardrails_triggered", [])
        state["guardrails_triggered"].append({
            "type": "pii_scrubbed",
            "details": pii_detections + title_pii,
        })
    
    # 3. Sanitize for LLM
    safe_title = sanitize_for_llm(scrubbed_title)
    safe_description = sanitize_for_llm(scrubbed_description)
    
    # --- Build LLM prompt ---
    user_prompt = f"""Incident Report:
Title: {safe_title}
Description: {safe_description}
"""
    
    # --- Prepare multimodal content ---
    model = _get_model()
    content_parts = [INTAKE_SYSTEM_PROMPT, user_prompt]
    
    # Check for image attachments
    image_included = False
    for attachment in attachments:
        filepath = attachment.get("path", "")
        original_name = attachment.get("original_name", "")
        
        if is_image_file(original_name) and os.path.exists(filepath):
            try:
                with open(filepath, "rb") as f:
                    image_bytes = f.read()
                
                # Determine MIME type
                ext = original_name.rsplit(".", 1)[-1].lower()
                mime_map = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp", "gif": "image/gif"}
                mime_type = mime_map.get(ext, "image/png")
                
                content_parts.append({
                    "mime_type": mime_type,
                    "data": image_bytes,
                })
                content_parts.append(IMAGE_ANALYSIS_PROMPT)
                image_included = True
                logger.info("📸 Including image attachment: %s", original_name)
            except Exception as e:
                logger.error("Failed to read image attachment: %s", e)
    
    # --- Call Gemini ---
    try:
        response = model.generate_content(
            content_parts,
            generation_config=genai.GenerationConfig(
                temperature=0.1,
                max_output_tokens=2048,
                response_mime_type="application/json",
            ),
        )
        
        result_text = response.text.strip()
        # Parse JSON response
        result = json.loads(result_text)
        
        logger.info("✅ Intake Agent: Extracted structured data — service=%s, severity=%s",
                     result.get("affected_service"), result.get("severity_hint"))
        
    except json.JSONDecodeError as e:
        logger.error("Failed to parse Gemini response as JSON: %s", e)
        logger.error("Raw response: %s", response.text[:500] if response else "None")
        result = _fallback_extraction(safe_title, safe_description)
    except Exception as e:
        logger.error("Gemini API call failed: %s", e)
        result = _fallback_extraction(safe_title, safe_description)
    
    # --- Update state ---
    state["structured_title"] = result.get("structured_title", safe_title)
    state["structured_description"] = result.get("structured_description", safe_description)
    state["affected_service"] = result.get("affected_service", "unknown")
    state["error_type"] = result.get("error_type", "unknown")
    state["severity_hint"] = result.get("severity_hint", "P3")
    state["extracted_error_codes"] = result.get("extracted_error_codes", [])
    state["extracted_stack_traces"] = result.get("extracted_stack_traces", [])
    state["keywords"] = result.get("keywords", [])
    state["visual_analysis"] = result.get("visual_analysis", None) if image_included else None
    
    return state


def _fallback_extraction(title: str, description: str) -> dict:
    """Fallback extraction when LLM is unavailable — uses simple heuristics."""
    logger.warning("Using fallback extraction (no LLM)")
    
    combined = f"{title} {description}".lower()
    
    # Simple service detection
    service = "unknown"
    if any(w in combined for w in ["checkout", "cart", "shipping"]):
        service = "checkout"
    elif any(w in combined for w in ["payment", "stripe", "charge", "refund"]):
        service = "payment"
    elif any(w in combined for w in ["order", "fulfill", "cancel"]):
        service = "order"
    elif any(w in combined for w in ["product", "stock", "inventory", "sku"]):
        service = "product"
    elif any(w in combined for w in ["graphql", "query", "mutation", "api"]):
        service = "graphql"
    
    # Simple error type detection
    error_type = "unknown"
    if "500" in combined or "internal server error" in combined:
        error_type = "500_error"
    elif "timeout" in combined or "504" in combined:
        error_type = "timeout"
    elif "payment" in combined and ("error" in combined or "fail" in combined):
        error_type = "payment_error"
    elif "stock" in combined or "insufficient" in combined:
        error_type = "stock_error"
    
    # Simple severity
    severity = "P3"
    if any(w in combined for w in ["outage", "all users", "critical", "down"]):
        severity = "P1"
    elif any(w in combined for w in ["many users", "major", "broken"]):
        severity = "P2"
    elif any(w in combined for w in ["cosmetic", "minor", "typo"]):
        severity = "P4"
    
    # Extract keywords (simple word extraction)
    keywords = list(set(
        w for w in combined.split()
        if len(w) > 3 and w not in {"the", "and", "for", "that", "this", "with", "from", "have", "been"}
    ))[:10]
    
    return {
        "structured_title": title,
        "structured_description": description,
        "affected_service": service,
        "error_type": error_type,
        "severity_hint": severity,
        "extracted_error_codes": [],
        "extracted_stack_traces": [],
        "keywords": keywords,
    }
