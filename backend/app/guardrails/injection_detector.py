"""
TriageForge — Prompt Injection Detector
Heuristic-based detection of prompt injection attempts in incident reports.
"""

import re
import logging

logger = logging.getLogger("triageforge.guardrails.injection")

# Patterns that indicate prompt injection attempts
INJECTION_PATTERNS = [
    # System prompt override attempts
    (r"ignore\s+(all\s+)?previous\s+instructions", "system_prompt_override"),
    (r"disregard\s+(all\s+)?prior\s+instructions", "system_prompt_override"),
    (r"forget\s+(everything|all)\s+(you|that)", "system_prompt_override"),
    (r"you\s+are\s+now\s+a", "role_override"),
    (r"act\s+as\s+(if\s+you\s+are|a)", "role_override"),
    (r"pretend\s+(to\s+be|you\s+are)", "role_override"),
    (r"new\s+system\s+prompt", "system_prompt_override"),
    (r"override\s+system\s+prompt", "system_prompt_override"),
    
    # Data exfiltration attempts
    (r"reveal\s+(your|the)\s+(system\s+)?prompt", "data_exfiltration"),
    (r"show\s+me\s+(your|the)\s+instructions", "data_exfiltration"),
    (r"what\s+are\s+your\s+instructions", "data_exfiltration"),
    (r"print\s+(your|the)\s+system\s+prompt", "data_exfiltration"),
    
    # Delimiter attacks
    (r"```system", "delimiter_attack"),
    (r"\[SYSTEM\]", "delimiter_attack"),
    (r"<\|system\|>", "delimiter_attack"),
    (r"<\|im_start\|>", "delimiter_attack"),
    
    # Encoded instruction attempts
    (r"base64\s*:", "encoded_instruction"),
    (r"eval\s*\(", "code_execution"),
    (r"exec\s*\(", "code_execution"),
    (r"__import__", "code_execution"),
]


def detect_prompt_injection(text: str) -> tuple[bool, list[dict]]:
    """
    Detect potential prompt injection attempts in input text.
    
    Uses heuristic pattern matching to identify common injection techniques.
    
    Args:
        text: The input text to analyze
        
    Returns:
        Tuple of (is_injection: bool, detections: list[dict])
        Each detection dict has: pattern_type, matched_text, position
    """
    if not text:
        return False, []

    detections = []
    text_lower = text.lower()

    for pattern, pattern_type in INJECTION_PATTERNS:
        matches = re.finditer(pattern, text_lower)
        for match in matches:
            detections.append({
                "pattern_type": pattern_type,
                "matched_text": match.group(),
                "position": match.start(),
            })

    is_injection = len(detections) > 0

    if is_injection:
        logger.warning(
            "Prompt injection detected: %d patterns matched — types: %s",
            len(detections),
            ", ".join(set(d["pattern_type"] for d in detections)),
        )

    return is_injection, detections


def sanitize_for_llm(text: str) -> str:
    """
    Sanitize text before sending to LLM to reduce injection risk.
    
    This doesn't fully prevent injection (impossible with heuristics alone),
    but reduces the attack surface by escaping common delimiter patterns.
    """
    # Escape common prompt delimiter patterns
    sanitized = text
    sanitized = re.sub(r'<\|[^|]+\|>', '[REMOVED_DELIMITER]', sanitized)
    sanitized = re.sub(r'```system', '```code', sanitized)
    sanitized = sanitized.replace("[SYSTEM]", "[TEXT]")
    sanitized = sanitized.replace("[INST]", "[TEXT]")
    
    return sanitized
