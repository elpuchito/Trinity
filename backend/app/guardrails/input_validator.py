"""
Trinity — Input Validator
File type and size validation for incident attachments.
"""

import logging
from fastapi import UploadFile

logger = logging.getLogger("triageforge.guardrails.validator")

# Allowed file types for incident attachments
ALLOWED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif",  # Images
    ".txt", ".log",                              # Text logs
    ".json", ".yaml", ".yml",                   # Config/data
    ".csv",                                      # Data exports
    ".html",                                     # Error pages
}

ALLOWED_CONTENT_TYPES = {
    "image/png", "image/jpeg", "image/webp", "image/gif",
    "text/plain", "text/html", "text/csv",
    "application/json", "application/x-yaml",
    "application/octet-stream",  # Generic binary (we check extension too)
}

# Maximum file size: 10MB
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024

# Image-specific extensions (triggers multimodal analysis)
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def validate_attachment(file: UploadFile) -> tuple[bool, str]:
    """
    Validate an uploaded file for type and size constraints.
    
    Args:
        file: The uploaded file to validate
        
    Returns:
        Tuple of (is_valid: bool, reason: str)
    """
    if not file.filename:
        return False, "File has no filename"

    # Check extension
    ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        return False, f"File type '{ext}' is not allowed. Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}"

    # Check content type
    if file.content_type and file.content_type not in ALLOWED_CONTENT_TYPES:
        logger.warning(
            "Suspicious content type '%s' for file '%s'",
            file.content_type, file.filename,
        )
        # Don't reject — content_type can be unreliable, we trust extension more

    return True, "OK"


async def validate_file_size(file: UploadFile) -> tuple[bool, str]:
    """
    Check file size against the maximum limit.
    
    Note: This reads the file content to check size, so call this
    before other processing to avoid double-reads.
    """
    content = await file.read()
    await file.seek(0)  # Reset for subsequent reads

    if len(content) > MAX_FILE_SIZE_BYTES:
        size_mb = len(content) / (1024 * 1024)
        return False, f"File size ({size_mb:.1f}MB) exceeds maximum ({MAX_FILE_SIZE_BYTES / (1024 * 1024):.0f}MB)"

    return True, "OK"


def is_image_file(filename: str) -> bool:
    """Check if a filename indicates an image file (for multimodal analysis)."""
    if not filename:
        return False
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in IMAGE_EXTENSIONS
