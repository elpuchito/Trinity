"""
TriageForge — Incidents API
CRUD endpoints for incident reports.
"""

import uuid
import os
import json
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Incident, IncidentStatus, SeverityLevel
from app.schemas import (
    IncidentCreate, IncidentUpdate, IncidentResponse,
    IncidentListResponse, PipelineStageUpdate
)

router = APIRouter(prefix="/api/incidents", tags=["incidents"])

# WebSocket connection manager for real-time updates
class ConnectionManager:
    """Manages WebSocket connections for real-time pipeline updates."""

    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, incident_id: str):
        await websocket.accept()
        if incident_id not in self.active_connections:
            self.active_connections[incident_id] = []
        self.active_connections[incident_id].append(websocket)

    def disconnect(self, websocket: WebSocket, incident_id: str):
        if incident_id in self.active_connections:
            self.active_connections[incident_id].remove(websocket)
            if not self.active_connections[incident_id]:
                del self.active_connections[incident_id]

    async def send_update(self, incident_id: str, data: dict):
        if incident_id in self.active_connections:
            for connection in self.active_connections[incident_id]:
                try:
                    await connection.send_json(data)
                except Exception:
                    pass

    async def broadcast(self, data: dict):
        for connections in self.active_connections.values():
            for connection in connections:
                try:
                    await connection.send_json(data)
                except Exception:
                    pass


manager = ConnectionManager()


# ============================================
# REST Endpoints
# ============================================

@router.post("", response_model=IncidentResponse, status_code=201)
async def create_incident(
    title: str = Form(...),
    description: str = Form(...),
    reporter_name: str = Form(...),
    reporter_email: str = Form(...),
    attachments: list[UploadFile] = File(default=[]),
    db: AsyncSession = Depends(get_db),
):
    """
    Submit a new incident report with optional file attachments.
    Triggers the agent triage pipeline asynchronously.
    """
    # Save attachments
    saved_files = []
    for attachment in attachments:
        if attachment.filename:
            file_ext = os.path.splitext(attachment.filename)[1]
            file_id = str(uuid.uuid4())
            file_path = f"/app/uploads/{file_id}{file_ext}"
            content = await attachment.read()
            with open(file_path, "wb") as f:
                f.write(content)
            saved_files.append({
                "id": file_id,
                "original_name": attachment.filename,
                "path": file_path,
                "content_type": attachment.content_type,
                "size": len(content),
            })

    # Create incident record
    incident = Incident(
        title=title,
        description=description,
        reporter_name=reporter_name,
        reporter_email=reporter_email,
        attachments=saved_files,
        status=IncidentStatus.SUBMITTED,
        severity=SeverityLevel.UNKNOWN,
    )
    db.add(incident)
    await db.flush()
    await db.refresh(incident, ["tickets", "notifications"])

    # Trigger agent pipeline asynchronously (in-process)
    import asyncio
    asyncio.create_task(
        _run_pipeline_and_persist(
            str(incident.id),
            title,
            description,
            reporter_name,
            reporter_email,
            saved_files,
        )
    )

    return incident


@router.get("", response_model=list[IncidentListResponse])
async def list_incidents(
    status: Optional[IncidentStatus] = None,
    severity: Optional[SeverityLevel] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """List all incidents with optional filtering."""
    query = select(Incident).order_by(desc(Incident.created_at))

    if status:
        query = query.where(Incident.status == status)
    if severity:
        query = query.where(Incident.severity == severity)

    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    incidents = result.scalars().all()
    return incidents


@router.get("/{incident_id}", response_model=IncidentResponse)
async def get_incident(
    incident_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a single incident with full details, tickets, and notifications."""
    query = (
        select(Incident)
        .where(Incident.id == incident_id)
        .options(
            selectinload(Incident.tickets),
            selectinload(Incident.notifications),
        )
    )
    result = await db.execute(query)
    incident = result.scalar_one_or_none()

    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    return incident


@router.patch("/{incident_id}", response_model=IncidentResponse)
async def update_incident(
    incident_id: uuid.UUID,
    update: IncidentUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update an incident (status, severity, assignment, etc.)."""
    query = (
        select(Incident)
        .where(Incident.id == incident_id)
        .options(
            selectinload(Incident.tickets),
            selectinload(Incident.notifications),
        )
    )
    result = await db.execute(query)
    incident = result.scalar_one_or_none()

    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    update_data = update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(incident, field, value)

    # Track resolution timestamp
    if update.status == IncidentStatus.RESOLVED and not incident.resolved_at:
        incident.resolved_at = datetime.now(timezone.utc)

    incident.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(incident, ["tickets", "notifications"])

    # Broadcast status update via WebSocket
    await manager.broadcast({
        "type": "incident_updated",
        "incident_id": str(incident_id),
        "status": incident.status.value,
        "severity": incident.severity.value if incident.severity else None,
    })

    return incident



# ============================================
# Pipeline Integration
# ============================================

async def _run_pipeline_and_persist(
    incident_id: str,
    title: str,
    description: str,
    reporter_name: str,
    reporter_email: str,
    attachments: list,
):
    """
    Run the triage pipeline and persist results to the database.
    Called as a fire-and-forget asyncio task from create_incident.
    """
    import logging
    from app.agents.pipeline import run_triage_pipeline
    from app.database import async_session
    from app.models import Incident, IncidentStatus, SeverityLevel, Ticket, Notification, NotificationChannel

    logger = logging.getLogger("triageforge.pipeline_runner")
    logger.info("🚀 Pipeline runner started for incident %s", incident_id)

    try:
        # Update status to TRIAGING
        async with async_session() as db:
            result = await db.execute(
                select(Incident).where(Incident.id == uuid.UUID(incident_id))
            )
            incident = result.scalar_one_or_none()
            if incident:
                incident.status = IncidentStatus.TRIAGING
                await db.commit()

        # Broadcast status update
        await manager.send_update(incident_id, {
            "type": "pipeline_started",
            "incident_id": incident_id,
            "stage": "intake",
            "status": "running",
        })

        # Run the full pipeline
        final_state = await run_triage_pipeline(
            incident_id=incident_id,
            title=title,
            description=description,
            reporter_name=reporter_name,
            reporter_email=reporter_email,
            attachments=attachments,
        )

        # Broadcast stage updates
        for stage in final_state.get("pipeline_stages", []):
            await manager.send_update(incident_id, {
                "type": "stage_update",
                "incident_id": incident_id,
                **stage,
            })
            await manager.broadcast({
                "type": "stage_update",
                "incident_id": incident_id,
                **stage,
            })

        # --- Persist results to database ---
        async with async_session() as db:
            result = await db.execute(
                select(Incident).where(Incident.id == uuid.UUID(incident_id))
            )
            incident = result.scalar_one_or_none()

            if not incident:
                logger.error("Incident %s not found after pipeline", incident_id)
                return

            # Map severity string to enum
            severity_map = {
                "P1": SeverityLevel.P1_CRITICAL,
                "P2": SeverityLevel.P2_HIGH,
                "P3": SeverityLevel.P3_MEDIUM,
                "P4": SeverityLevel.P4_LOW,
            }
            final_sev = final_state.get("final_severity", "P3")

            # Update incident with triage results
            incident.severity = severity_map.get(final_sev, SeverityLevel.P3_MEDIUM)
            incident.status = IncidentStatus.TRIAGED
            incident.assigned_team = final_state.get("assigned_team", "sre-oncall")
            incident.affected_service = final_state.get("affected_service", "unknown")
            incident.root_cause_hypothesis = final_state.get("code_root_cause", "")
            incident.suggested_runbook = final_state.get("suggested_runbook", "")
            incident.related_code_files = final_state.get("related_code_files", [])
            incident.is_duplicate = final_state.get("is_duplicate", False)

            dup_id = final_state.get("duplicate_of_id")
            if dup_id:
                try:
                    incident.duplicate_of_id = uuid.UUID(dup_id)
                except (ValueError, TypeError):
                    pass

            # Build full triage report JSON
            incident.triage_report = {
                "severity": final_sev,
                "affected_service": final_state.get("affected_service"),
                "error_type": final_state.get("error_type"),
                "root_cause_hypothesis": final_state.get("code_root_cause"),
                "code_confidence": final_state.get("code_confidence", 0),
                "suggested_runbook": final_state.get("suggested_runbook"),
                "known_issues": final_state.get("known_issues", []),
                "related_code_files": final_state.get("related_code_files", []),
                "triage_summary": final_state.get("triage_summary", ""),
                "recommended_actions": final_state.get("recommended_actions", []),
                "routing_rationale": final_state.get("routing_rationale", ""),
                "is_duplicate": final_state.get("is_duplicate", False),
                "related_incidents": final_state.get("related_incidents", []),
                "pipeline_stages": final_state.get("pipeline_stages", []),
                "errors": final_state.get("errors", []),
                "guardrails_triggered": final_state.get("guardrails_triggered", []),
                "pipeline_start_time": final_state.get("pipeline_start_time"),
                "pipeline_end_time": final_state.get("pipeline_end_time"),
            }

            # Create mocked ticket
            ticket = Ticket(
                incident_id=incident.id,
                external_id=f"TF-{str(incident.id)[:8].upper()}",
                external_url=f"https://linear.app/triageforge/issue/TF-{str(incident.id)[:8].upper()}",
                title=final_state.get("structured_title", title),
                priority=final_sev,
                assignee=final_state.get("assigned_team", "sre-oncall"),
                labels=[
                    final_state.get("affected_service", "unknown"),
                    final_state.get("error_type", "unknown"),
                    final_sev,
                ],
            )
            db.add(ticket)

            # Create notifications
            for notif in final_state.get("notification_plan", []):
                channel = NotificationChannel.SLACK if notif.get("channel") == "slack" else NotificationChannel.EMAIL
                notification = Notification(
                    incident_id=incident.id,
                    channel=channel,
                    recipient=notif.get("recipient", ""),
                    subject=f"[{final_sev}] {final_state.get('structured_title', title)[:100]}",
                    message=final_state.get("triage_summary", "Incident triaged."),
                    is_sent=True,
                    sent_at=datetime.now(timezone.utc),
                )
                db.add(notification)

            incident.status = IncidentStatus.TICKET_CREATED
            await db.commit()
            logger.info("✅ Pipeline results persisted for incident %s", incident_id)

        # Final broadcast
        await manager.send_update(incident_id, {
            "type": "pipeline_completed",
            "incident_id": incident_id,
            "severity": final_sev,
            "assigned_team": final_state.get("assigned_team"),
            "triage_summary": final_state.get("triage_summary", ""),
        })
        await manager.broadcast({
            "type": "incident_triaged",
            "incident_id": incident_id,
            "severity": final_sev,
            "status": "ticket_created",
        })

    except Exception as e:
        logger.error("Pipeline runner failed for %s: %s", incident_id, e, exc_info=True)
        # Try to update incident status to reflect error
        try:
            async with async_session() as db:
                result = await db.execute(
                    select(Incident).where(Incident.id == uuid.UUID(incident_id))
                )
                incident = result.scalar_one_or_none()
                if incident:
                    incident.triage_report = {"error": str(e), "status": "pipeline_failed"}
                    incident.status = IncidentStatus.TRIAGED
                    await db.commit()
        except Exception:
            pass


@router.get("/{incident_id}/pipeline-status")
async def get_pipeline_status(
    incident_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get the triage pipeline status for an incident."""
    result = await db.execute(
        select(Incident).where(Incident.id == incident_id)
    )
    incident = result.scalar_one_or_none()

    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    triage_report = incident.triage_report or {}
    return {
        "incident_id": str(incident.id),
        "status": incident.status.value if incident.status else "unknown",
        "severity": incident.severity.value if incident.severity else "unknown",
        "pipeline_stages": triage_report.get("pipeline_stages", []),
        "errors": triage_report.get("errors", []),
        "triage_summary": triage_report.get("triage_summary", ""),
    }


# ============================================
# WebSocket for real-time pipeline updates
# ============================================

@router.websocket("/ws/{incident_id}")
async def websocket_pipeline(websocket: WebSocket, incident_id: str):
    """WebSocket endpoint for real-time triage pipeline updates."""
    await manager.connect(websocket, incident_id)
    try:
        while True:
            # Keep connection alive, receive any client messages
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, incident_id)


@router.websocket("/ws")
async def websocket_global(websocket: WebSocket):
    """Global WebSocket for dashboard-level updates."""
    await manager.connect(websocket, "__global__")
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, "__global__")

