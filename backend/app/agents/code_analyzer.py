"""
Trinity — Code Analyzer Agent
RAG-powered agent that searches the Saleor codebase to find relevant
source code and hypothesize root causes.
"""

import json
import logging

import google.generativeai as genai

from app.config import get_settings
from app.rag.retriever import search_code

logger = logging.getLogger("triageforge.agents.code_analyzer")

CODE_ANALYSIS_PROMPT = """You are an expert SRE code analyst for the Saleor e-commerce platform (Python/Django).

Given an incident report and relevant source code snippets retrieved from the codebase, analyze the code to:

1. Identify which files and functions are most likely involved in the issue
2. Hypothesize the root cause based on code patterns, error handling, and documented known issues
3. Assess your confidence in the hypothesis (0.0 to 1.0)

Incident Context:
- Title: {title}
- Description: {description}
- Affected Service: {affected_service}
- Error Type: {error_type}
- Error Codes: {error_codes}
- Keywords: {keywords}

Retrieved Code Snippets:
{code_snippets}

Respond with ONLY a valid JSON object:
{{
    "related_code_files": ["file1.py", "file2.py"],
    "code_root_cause": "A detailed hypothesis of the root cause based on the code analysis",
    "code_confidence": 0.85,
    "relevant_functions": ["function_name_1", "function_name_2"],
    "code_analysis_summary": "Brief summary of the code analysis"
}}"""


def _get_model():
    settings = get_settings()
    genai.configure(api_key=settings.google_api_key)
    return genai.GenerativeModel("gemini-3.1-flash-lite-preview")


async def run_code_analysis(state: dict) -> dict:
    """
    Analyze the Saleor codebase to find relevant code and hypothesize root cause.
    
    Uses RAG to retrieve relevant code chunks, then feeds them to Gemini
    for analysis.
    """
    logger.info("🔎 Code Analyzer Agent: Searching codebase...")
    
    # Build search queries from state
    affected_service = state.get("affected_service", "unknown")
    error_type = state.get("error_type", "unknown")
    keywords = state.get("keywords", [])
    error_codes = state.get("extracted_error_codes", [])
    title = state.get("structured_title", state.get("raw_title", ""))
    description = state.get("structured_description", state.get("raw_description", ""))
    
    # Construct multiple search queries for coverage
    queries = [
        f"{affected_service} {error_type}",
        f"{' '.join(keywords[:5])}",
        f"{title}",
    ]
    if error_codes:
        queries.append(f"{' '.join(error_codes[:3])}")
    
    # --- RAG search ---
    all_code_results = []
    seen_files = set()
    
    for query in queries:
        results = await search_code(query, n_results=3)
        for r in results:
            if r.file_path not in seen_files:
                all_code_results.append(r)
                seen_files.add(r.file_path)
    
    # Limit to top 8 results
    all_code_results = all_code_results[:8]
    
    if not all_code_results:
        logger.warning("No code results found in RAG search")
        state["related_code_files"] = []
        state["code_root_cause"] = "Unable to find relevant code in the codebase."
        state["code_confidence"] = 0.0
        state["code_analysis_summary"] = "No relevant code found."
        return state
    
    # Format code snippets for the LLM
    code_snippets = ""
    for i, result in enumerate(all_code_results, 1):
        code_snippets += f"\n--- Snippet {i} (from {result.file_path}, relevance: {result.relevance_score}) ---\n"
        code_snippets += result.content[:1500]  # Limit per snippet
        code_snippets += "\n"
    
    # --- Call Gemini ---
    prompt = CODE_ANALYSIS_PROMPT.format(
        title=title,
        description=description,
        affected_service=affected_service,
        error_type=error_type,
        error_codes=", ".join(error_codes) if error_codes else "none",
        keywords=", ".join(keywords),
        code_snippets=code_snippets,
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
        
        state["related_code_files"] = result.get("related_code_files", [])
        state["code_root_cause"] = result.get("code_root_cause", "Unknown")
        state["code_confidence"] = result.get("code_confidence", 0.5)
        state["code_analysis_summary"] = result.get("code_analysis_summary", "")
        
        logger.info(
            "✅ Code Analyzer: Found %d relevant files, confidence=%.2f",
            len(state["related_code_files"]), state["code_confidence"],
        )
        
    except Exception as e:
        logger.error("Code analysis LLM call failed: %s", e)
        # Fallback: use RAG results directly
        state["related_code_files"] = [r.file_path for r in all_code_results[:5]]
        state["code_root_cause"] = f"RAG search found relevant code in: {', '.join(state['related_code_files'][:3])}"
        state["code_confidence"] = 0.3
        state["code_analysis_summary"] = "Analysis based on RAG search results only (LLM unavailable)."
    
    return state
