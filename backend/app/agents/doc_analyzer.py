"""
TriageForge — Doc Analyzer Agent
RAG-powered agent that searches documentation and runbooks for
mitigation steps, known issues, and historical context.
"""

import json
import logging

import google.generativeai as genai

from app.config import get_settings
from app.rag.retriever import search_docs

logger = logging.getLogger("triageforge.agents.doc_analyzer")

DOC_ANALYSIS_PROMPT = """You are an expert SRE documentation analyst for the Saleor e-commerce platform.

Given an incident report and relevant documentation/runbooks retrieved from the knowledge base, provide:

1. Suggested runbook steps for resolving this incident
2. Any known issues that match this incident pattern
3. References to relevant documentation

Incident Context:
- Title: {title}
- Description: {description}
- Affected Service: {affected_service}
- Error Type: {error_type}
- Error Codes: {error_codes}
- Root Cause Hint: {root_cause_hint}

Retrieved Documentation:
{doc_snippets}

Respond with ONLY a valid JSON object:
{{
    "suggested_runbook": "Step-by-step runbook for resolving this incident:\\n1. First step...\\n2. Second step...",
    "known_issues": ["Known issue 1 that matches", "Known issue 2"],
    "doc_references": ["docs/runbooks/checkout_failures.md", "docs/common_errors.md"],
    "mitigation_summary": "Brief summary of recommended mitigation approach",
    "estimated_resolution_time": "15-30 minutes"
}}"""


def _get_model():
    settings = get_settings()
    genai.configure(api_key=settings.google_api_key)
    return genai.GenerativeModel("gemini-3.1-flash-lite-preview")


async def run_doc_analysis(state: dict) -> dict:
    """
    Search documentation and runbooks for relevant mitigation steps.
    """
    logger.info("📚 Doc Analyzer Agent: Searching documentation...")
    
    affected_service = state.get("affected_service", "unknown")
    error_type = state.get("error_type", "unknown")
    keywords = state.get("keywords", [])
    error_codes = state.get("extracted_error_codes", [])
    title = state.get("structured_title", state.get("raw_title", ""))
    description = state.get("structured_description", state.get("raw_description", ""))
    root_cause_hint = state.get("code_root_cause", "not yet analyzed")
    
    # Build search queries
    queries = [
        f"{affected_service} {error_type} runbook",
        f"{title}",
        f"{' '.join(keywords[:5])} troubleshooting",
    ]
    if error_codes:
        queries.append(f"{' '.join(error_codes[:3])} resolution")
    
    # --- RAG search ---
    all_doc_results = []
    seen_docs = set()
    
    for query in queries:
        results = await search_docs(query, n_results=3)
        for r in results:
            doc_key = f"{r.file_path}:{r.metadata.get('heading', '')}"
            if doc_key not in seen_docs:
                all_doc_results.append(r)
                seen_docs.add(doc_key)
    
    all_doc_results = all_doc_results[:8]
    
    if not all_doc_results:
        logger.warning("No documentation found in RAG search")
        state["suggested_runbook"] = "No specific runbook found. Follow general incident response procedure."
        state["known_issues"] = []
        state["doc_references"] = []
        return state
    
    # Format doc snippets
    doc_snippets = ""
    for i, result in enumerate(all_doc_results, 1):
        heading = result.metadata.get("heading", "")
        doc_snippets += f"\n--- Document {i}: {heading} (from {result.file_path}, relevance: {result.relevance_score}) ---\n"
        doc_snippets += result.content[:2000]
        doc_snippets += "\n"
    
    # --- Call Gemini ---
    prompt = DOC_ANALYSIS_PROMPT.format(
        title=title,
        description=description,
        affected_service=affected_service,
        error_type=error_type,
        error_codes=", ".join(error_codes) if error_codes else "none",
        root_cause_hint=root_cause_hint,
        doc_snippets=doc_snippets,
    )
    
    try:
        model = _get_model()
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.1,
                max_output_tokens=2048,
                response_mime_type="application/json",
            ),
        )
        
        result = json.loads(response.text.strip())
        
        state["suggested_runbook"] = result.get("suggested_runbook", "No runbook available.")
        state["known_issues"] = result.get("known_issues", [])
        state["doc_references"] = result.get("doc_references", [])
        state["mitigation_summary"] = result.get("mitigation_summary", "")
        state["estimated_resolution_time"] = result.get("estimated_resolution_time", "unknown")
        
        logger.info(
            "✅ Doc Analyzer: Found %d known issues, %d doc references",
            len(state["known_issues"]), len(state["doc_references"]),
        )
        
    except Exception as e:
        logger.error("Doc analysis LLM call failed: %s", e)
        # Fallback: present raw doc results
        state["suggested_runbook"] = "LLM unavailable. Relevant docs found:\n" + "\n".join(
            f"- {r.file_path}: {r.metadata.get('heading', 'N/A')}"
            for r in all_doc_results[:5]
        )
        state["known_issues"] = []
        state["doc_references"] = [r.file_path for r in all_doc_results[:5]]
    
    return state
