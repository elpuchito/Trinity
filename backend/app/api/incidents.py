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

    # TODO: Trigger agent pipeline asynchronously (Phase 2)
    # await trigger_triage_pipeline(incident.id)

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
