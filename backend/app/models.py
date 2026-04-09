"""
Trinity — SQLAlchemy Models
Core data models: Incident, Ticket, Notification, TriageResult
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Text, DateTime, Integer, ForeignKey,
    Enum as SQLEnum, JSON, Boolean
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum

from app.database import Base


# ============================================
# Enums
# ============================================

class SeverityLevel(str, enum.Enum):
    P1_CRITICAL = "P1"
    P2_HIGH = "P2"
    P3_MEDIUM = "P3"
    P4_LOW = "P4"
    UNKNOWN = "UNKNOWN"


class IncidentStatus(str, enum.Enum):
    SUBMITTED = "submitted"
    TRIAGING = "triaging"
    TRIAGED = "triaged"
    TICKET_CREATED = "ticket_created"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class NotificationChannel(str, enum.Enum):
    EMAIL = "email"
    SLACK = "slack"


class TicketStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


# ============================================
# Models
# ============================================

class Incident(Base):
    """An incident report submitted by a user."""
    __tablename__ = "incidents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=False)
    severity = Column(SQLEnum(SeverityLevel), default=SeverityLevel.UNKNOWN)
    status = Column(SQLEnum(IncidentStatus), default=IncidentStatus.SUBMITTED)

    # Reporter info
    reporter_name = Column(String(200), nullable=False)
    reporter_email = Column(String(300), nullable=False)

    # Attachments (stored as JSON list of file paths)
    attachments = Column(JSON, default=list)

    # Agent-produced triage data
    triage_report = Column(JSON, nullable=True)
    assigned_team = Column(String(200), nullable=True)
    affected_service = Column(String(200), nullable=True)
    root_cause_hypothesis = Column(Text, nullable=True)
    suggested_runbook = Column(Text, nullable=True)
    related_code_files = Column(JSON, nullable=True)
    is_duplicate = Column(Boolean, default=False)
    duplicate_of_id = Column(UUID(as_uuid=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    tickets = relationship("Ticket", back_populates="incident", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="incident", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Incident {self.id} [{self.severity}] {self.title[:50]}>"


class Ticket(Base):
    """A ticket created in the external ticketing system (mocked)."""
    __tablename__ = "tickets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id = Column(UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=False)

    # External ticket system data
    external_id = Column(String(100), nullable=False)
    external_url = Column(String(500), nullable=False)
    title = Column(String(500), nullable=False)
    status = Column(SQLEnum(TicketStatus), default=TicketStatus.OPEN)
    priority = Column(String(50), nullable=True)
    assignee = Column(String(200), nullable=True)
    labels = Column(JSON, default=list)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    incident = relationship("Incident", back_populates="tickets")

    def __repr__(self):
        return f"<Ticket {self.external_id} [{self.status}]>"


class Notification(Base):
    """A notification sent to engineers or reporters."""
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id = Column(UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=False)

    channel = Column(SQLEnum(NotificationChannel), nullable=False)
    recipient = Column(String(300), nullable=False)
    subject = Column(String(500), nullable=True)
    message = Column(Text, nullable=False)
    is_sent = Column(Boolean, default=False)

    # Timestamps
    sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    incident = relationship("Incident", back_populates="notifications")

    def __repr__(self):
        return f"<Notification {self.channel} -> {self.recipient}>"
