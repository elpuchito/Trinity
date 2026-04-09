"""
Trinity — Pydantic Schemas
Request/Response models for the API.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field

from app.models import SeverityLevel, IncidentStatus, TicketStatus, NotificationChannel


# ============================================
# Incident Schemas
# ============================================

class IncidentCreate(BaseModel):
    """Schema for creating a new incident report."""
    title: str = Field(..., min_length=5, max_length=500, description="Brief title of the incident")
    description: str = Field(..., min_length=10, description="Detailed description of the incident")
    reporter_name: str = Field(..., min_length=2, max_length=200)
    reporter_email: str = Field(..., max_length=300)

    model_config = {"json_schema_extra": {
        "example": {
            "title": "Checkout page returns 500 error",
            "description": "Users are seeing a 500 Internal Server Error when clicking 'Place Order'. The error occurs after entering payment details. Console shows: 'TypeError: Cannot read property total_gross_amount of undefined'.",
            "reporter_name": "Jane Smith",
            "reporter_email": "jane@example.com",
        }
    }}


class IncidentUpdate(BaseModel):
    """Schema for updating an incident."""
    status: Optional[IncidentStatus] = None
    severity: Optional[SeverityLevel] = None
    assigned_team: Optional[str] = None
    triage_report: Optional[dict] = None


class TriageReport(BaseModel):
    """Structured triage report produced by the agent pipeline."""
    severity: SeverityLevel
    affected_service: str
    root_cause_hypothesis: str
    suggested_runbook: str
    related_code_files: list[str] = []
    confidence_score: float = Field(ge=0.0, le=1.0)
    assigned_team: str
    summary: str
    is_duplicate: bool = False
    duplicate_of_id: Optional[UUID] = None
    tags: list[str] = []


class TicketResponse(BaseModel):
    """Schema for ticket data in responses."""
    id: UUID
    external_id: str
    external_url: str
    title: str
    status: TicketStatus
    priority: Optional[str]
    assignee: Optional[str]
    labels: list[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationResponse(BaseModel):
    """Schema for notification data in responses."""
    id: UUID
    channel: NotificationChannel
    recipient: str
    subject: Optional[str]
    message: str
    is_sent: bool
    sent_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class IncidentResponse(BaseModel):
    """Full incident response with triage data, tickets, and notifications."""
    id: UUID
    title: str
    description: str
    severity: SeverityLevel
    status: IncidentStatus
    reporter_name: str
    reporter_email: str
    attachments: list[dict] = []
    triage_report: Optional[dict]
    assigned_team: Optional[str]
    affected_service: Optional[str]
    root_cause_hypothesis: Optional[str]
    suggested_runbook: Optional[str]
    related_code_files: Optional[list[str]]
    is_duplicate: bool
    duplicate_of_id: Optional[UUID]
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime]
    tickets: list[TicketResponse] = []
    notifications: list[NotificationResponse] = []

    model_config = {"from_attributes": True}


class IncidentListResponse(BaseModel):
    """Lightweight incident for list views."""
    id: UUID
    title: str
    severity: SeverityLevel
    status: IncidentStatus
    reporter_name: str
    assigned_team: Optional[str]
    affected_service: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ============================================
# Pipeline Status (for WebSocket updates)
# ============================================

class PipelineStageUpdate(BaseModel):
    """Real-time update for a single pipeline stage."""
    incident_id: UUID
    stage: str  # intake, triage, code_analysis, doc_analysis, dedup, routing
    status: str  # pending, running, completed, error
    message: Optional[str] = None
    data: Optional[dict] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now())
