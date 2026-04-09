"""
TriageForge — PII Scrubber
Regex-based PII detection and masking for incident reports.
"""

import re
import logging

logger = logging.getLogger("triageforge.guardrails.pii")

# PII patterns with named groups
PII_PATTERNS = [
    # Credit card numbers (major networks)
    {
        "name": "credit_card",
        "pattern": r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b",
        "replacement": "[REDACTED_CC]",
    },
    # SSN (US Social Security Number)
    {
        "name": "ssn",
        "pattern": r"\b\d{3}-\d{2}-\d{4}\b",
        "replacement": "[REDACTED_SSN]",
    },
    # Phone numbers (various formats)
    {
        "name": "phone",
        "pattern": r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
        "replacement": "[REDACTED_PHONE]",
    },
    # Email addresses — preserve domain for triage context
    {
        "name": "email",
        "pattern": r"\b[a-zA-Z0-9._%+-]+@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b",
        "replacement": r"[REDACTED_EMAIL]@\1",
    },
    # IP addresses (IPv4)
    {
        "name": "ip_address",
        "pattern": r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b",
        "replacement": "[REDACTED_IP]",
    },
    # API keys (generic long alphanumeric strings that look like keys)
    {
        "name": "api_key",
        "pattern": r"\b(?:sk|pk|api|key|token|secret|password)[_-]?[a-zA-Z0-9]{20,}\b",
        "replacement": "[REDACTED_API_KEY]",
    },
]

# Whitelist: patterns that look like PII but aren't (e.g., error codes, UUIDs)
WHITELIST_PATTERNS = [
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",  # UUID
    r"\b(?:HTTP|http)[/ ]\d{3}\b",  # HTTP status codes
    r"\bport\s*\d{2,5}\b",  # Port numbers
]


def scrub_pii(text: str) -> tuple[str, list[dict]]:
    """
    Detect and mask PII in text.
    
    Args:
        text: The input text to scrub
        
    Returns:
        Tuple of (scrubbed_text, detections)
        Each detection dict has: pii_type, count
    """
    if not text:
        return text, []

    scrubbed = text
    detections = []

    for pii_def in PII_PATTERNS:
        matches = re.findall(pii_def["pattern"], scrubbed)
        if matches:
            count = len(matches)
            scrubbed = re.sub(pii_def["pattern"], pii_def["replacement"], scrubbed)
            detections.append({
                "pii_type": pii_def["name"],
                "count": count,
            })
            logger.info(
                "PII detected and scrubbed: %s (%d occurrences)",
                pii_def["name"], count,
            )

    return scrubbed, detections
