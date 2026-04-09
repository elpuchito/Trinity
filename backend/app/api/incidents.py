"""
TriageForge — Incidents API
CRUD endpoints for incident reports.
Integrated with mocked Linear, Slack, and Email services.
"""

import uuid
import os
import json
import logging
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
from app.integrations import linear_service, slack_service, email_service
from app.observability.tracing import get_tracer
from app.observability.metrics import (
    INCIDENTS_CREATED, GUARDRAILS_TRIGGERED,
    NOTIFICATIONS_SENT, TICKETS_CREATED, INCIDENTS_RESOLVED,
)
from app.guardrails.injection_detector import detect_prompt_injection, sanitize_for_llm
from app.guardrails.pii_scrubber import scrub_pii
from app.guardrails.input_validator import validate_attachment, validate_file_size

logger = logging.getLogger("triageforge.api.incidents")
tracer = get_tracer("triageforge.api")

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
    with tracer.start_as_current_span("api.create_incident") as span:
        span.set_attribute("reporter.email", reporter_email)
        span.set_attribute("attachments.count", len(attachments))

        # === Guardrails: Validate attachments ===
        for attachment in attachments:
            if attachment.filename:
                is_valid, reason = validate_attachment(attachment)
                if not is_valid:
                    GUARDRAILS_TRIGGERED.labels(guardrail_type="validation").inc()
                    span.set_attribute("guardrail.validation_blocked", True)
                    raise HTTPException(400, detail=f"Invalid attachment '{attachment.filename}': {reason}")
                size_ok, size_reason = await validate_file_size(attachment)
                if not size_ok:
                    GUARDRAILS_TRIGGERED.labels(guardrail_type="validation").inc()
                    span.set_attribute("guardrail.validation_blocked", True)
                    raise HTTPException(400, detail=size_reason)

        # === Guardrails: Prompt injection check ===
        combined_text = f"{title} {description}"
        is_injection, injection_detections = detect_prompt_injection(combined_text)
        guardrails_report = []
        if is_injection:
            GUARDRAILS_TRIGGERED.labels(guardrail_type="injection").inc()
            span.set_attribute("guardrail.injection_detected", True)
            span.set_attribute("guardrail.injection_patterns", len(injection_detections))
            description = sanitize_for_llm(description)
            title = sanitize_for_llm(title)
            guardrails_report.append({
                "type": "injection",
                "detections": injection_detections,
            })
            logger.warning("Prompt injection detected in incident from %s", reporter_email)

        # === Guardrails: PII scrubbing ===
        scrubbed_desc, pii_detections = scrub_pii(description)
        scrubbed_title, title_pii = scrub_pii(title)
        if pii_detections or title_pii:
            GUARDRAILS_TRIGGERED.labels(guardrail_type="pii").inc()
            span.set_attribute("guardrail.pii_scrubbed", True)
            guardrails_report.append({
                "type": "pii",
                "detections": pii_detections + title_pii,
            })

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

        # Create incident record (use scrubbed text for agent processing)
        incident = Incident(
            title=scrubbed_title,
            description=scrubbed_desc,
            reporter_name=reporter_name,
            reporter_email=reporter_email,
            attachments=saved_files,
            status=IncidentStatus.SUBMITTED,
            severity=SeverityLevel.UNKNOWN,
        )
        db.add(incident)
        await db.flush()
        await db.refresh(incident, ["tickets", "notifications"])

        span.set_attribute("incident.id", str(incident.id))
        INCIDENTS_CREATED.inc()

        # Trigger agent pipeline asynchronously (in-process)
        import asyncio
        asyncio.create_task(
            _run_pipeline_and_persist(
                str(incident.id),
                scrubbed_title,
                scrubbed_desc,
                reporter_name,
                reporter_email,
                saved_files,
                guardrails_report,
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
    """Update an incident (status, severity, assignment, etc.).
    When status transitions to RESOLVED, triggers resolution notifications."""
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

    is_resolving = (
        update.status == IncidentStatus.RESOLVED
        and incident.status != IncidentStatus.RESOLVED
    )

    update_data = update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(incident, field, value)

    # Track resolution timestamp
    if update.status == IncidentStatus.RESOLVED and not incident.resolved_at:
        incident.resolved_at = datetime.now(timezone.utc)

    incident.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(incident, ["tickets", "notifications"])

    # === Resolution Webhook Flow ===
    if is_resolving:
        await _handle_resolution(
            incident_id=str(incident_id),
            title=incident.title,
            severity=incident.severity.value if incident.severity else "P3",
            reporter_name=incident.reporter_name,
            reporter_email=incident.reporter_email,
            db=db,
            incident=incident,
        )

    # Broadcast status update via WebSocket
    await manager.broadcast({
        "type": "incident_resolved" if is_resolving else "incident_updated",
        "incident_id": str(incident_id),
        "status": incident.status.value,
        "severity": incident.severity.value if incident.severity else None,
    })

    return incident



# ============================================
# Pipeline Integration (with Mock Services)
# ============================================

async def _stage_broadcast_callback(incident_id: str, stage_data: dict):
    """WebSocket callback for real-time pipeline stage broadcasting."""
    await manager.send_update(incident_id, stage_data)
    await manager.broadcast(stage_data)


async def _run_pipeline_and_persist(
    incident_id: str,
    title: str,
    description: str,
    reporter_name: str,
    reporter_email: str,
    attachments: list,
    guardrails_report: list = None,
):
    """
    Run the triage pipeline and persist results to the database.
    Uses mocked Linear, Slack, and Email services for integrations.
    Called as a fire-and-forget asyncio task from create_incident.
    """
    from app.agents.pipeline import run_triage_pipeline
    from app.database import async_session
    from app.models import Incident, IncidentStatus, SeverityLevel, Ticket, Notification, NotificationChannel

    logger.info("🚀 Pipeline runner started for incident %s", incident_id)

    with tracer.start_as_current_span("api.pipeline_runner") as span:
        span.set_attribute("incident.id", incident_id)
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

            # Broadcast pipeline start
            await manager.send_update(incident_id, {
                "type": "pipeline_started",
                "incident_id": incident_id,
                "stage": "intake",
                "status": "running",
            })

            # Run the full pipeline with real-time stage callback
            final_state = await run_triage_pipeline(
                incident_id=incident_id,
                title=title,
                description=description,
                reporter_name=reporter_name,
                reporter_email=reporter_email,
                attachments=attachments,
                stage_callback=_stage_broadcast_callback,
            )

            # --- Extract pipeline results ---
            severity_map = {
                "P1": SeverityLevel.P1_CRITICAL,
                "P2": SeverityLevel.P2_HIGH,
                "P3": SeverityLevel.P3_MEDIUM,
                "P4": SeverityLevel.P4_LOW,
            }
            final_sev = final_state.get("final_severity", "P3")
            assigned_team = final_state.get("assigned_team", "sre-oncall")
            affected_service = final_state.get("affected_service", "unknown")
            triage_summary = final_state.get("triage_summary", "")
            recommended_actions = final_state.get("recommended_actions", [])

            # === 1. Create ticket via Linear Mock Service ===
            linear_issue = linear_service.create_issue(
                title=final_state.get("structured_title", title),
                description=triage_summary,
                priority=final_sev,
                assignee=assigned_team,
                labels=[
                    affected_service,
                    final_state.get("error_type", "unknown"),
                    final_sev,
                ],
                incident_id=incident_id,
            )
            logger.info("📋 Ticket created: %s", linear_issue["identifier"])
            TICKETS_CREATED.inc()

            # === 2. Send Slack notifications via Mock Service ===
            for notif in final_state.get("notification_plan", []):
                if notif.get("channel") == "slack":
                    slack_msg = slack_service.format_incident_message(
                        incident_id=incident_id,
                        title=final_state.get("structured_title", title),
                        severity=final_sev,
                        affected_service=affected_service,
                        assigned_team=assigned_team,
                        triage_summary=triage_summary,
                        recommended_actions=recommended_actions,
                        is_duplicate=final_state.get("is_duplicate", False),
                    )
                    slack_service.send_message(
                        channel=notif.get("recipient", "#incidents"),
                        text=slack_msg["text"],
                        blocks=slack_msg["blocks"],
                        incident_id=incident_id,
                        urgency=notif.get("urgency", "normal"),
                    )
                    NOTIFICATIONS_SENT.labels(channel="slack").inc()

            # === 3. Send Email notifications via Mock Service ===
            for notif in final_state.get("notification_plan", []):
                if notif.get("channel") == "email":
                    recipient = notif.get("recipient", "")
                    urgency = notif.get("urgency", "normal")

                    if urgency == "confirmation":
                        email_content = email_service.format_reporter_confirmation(
                            incident_id=incident_id,
                            title=final_state.get("structured_title", title),
                            severity=final_sev,
                            reporter_name=reporter_name,
                            ticket_id=linear_issue["identifier"],
                        )
                    else:
                        email_content = email_service.format_oncall_alert(
                            incident_id=incident_id,
                            title=final_state.get("structured_title", title),
                            severity=final_sev,
                            affected_service=affected_service,
                            assigned_team=assigned_team,
                            triage_summary=triage_summary,
                            runbook_steps=final_state.get("suggested_runbook", ""),
                            recommended_actions=recommended_actions,
                        )

                    email_service.send_email(
                        to=recipient,
                        subject=email_content["subject"],
                        html_body=email_content["html_body"],
                        incident_id=incident_id,
                        email_type="confirmation" if urgency == "confirmation" else "oncall_alert",
                    )
                    NOTIFICATIONS_SENT.labels(channel="email").inc()

            # === 4. Persist everything to database ===
            async with async_session() as db:
                result = await db.execute(
                    select(Incident).where(Incident.id == uuid.UUID(incident_id))
                )
                incident = result.scalar_one_or_none()

                if not incident:
                    logger.error("Incident %s not found after pipeline", incident_id)
                    return

                # Update incident with triage results
                incident.severity = severity_map.get(final_sev, SeverityLevel.P3_MEDIUM)
                incident.status = IncidentStatus.TRIAGED
                incident.assigned_team = assigned_team
                incident.affected_service = affected_service
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
                    "affected_service": affected_service,
                    "error_type": final_state.get("error_type"),
                    "root_cause_hypothesis": final_state.get("code_root_cause"),
                    "code_confidence": final_state.get("code_confidence", 0),
                    "suggested_runbook": final_state.get("suggested_runbook"),
                    "known_issues": final_state.get("known_issues", []),
                    "related_code_files": final_state.get("related_code_files", []),
                    "triage_summary": triage_summary,
                    "recommended_actions": recommended_actions,
                    "routing_rationale": final_state.get("routing_rationale", ""),
                    "is_duplicate": final_state.get("is_duplicate", False),
                    "related_incidents": final_state.get("related_incidents", []),
                    "pipeline_stages": final_state.get("pipeline_stages", []),
                    "errors": final_state.get("errors", []),
                    "guardrails_triggered": guardrails_report or final_state.get("guardrails_triggered", []),
                    "pipeline_start_time": final_state.get("pipeline_start_time"),
                    "pipeline_end_time": final_state.get("pipeline_end_time"),
                }

                # Persist ticket record (from Linear mock response)
                ticket = Ticket(
                    incident_id=incident.id,
                    external_id=linear_issue["identifier"],
                    external_url=linear_issue["url"],
                    title=linear_issue["title"],
                    priority=final_sev,
                    assignee=assigned_team,
                    labels=[
                        affected_service,
                        final_state.get("error_type", "unknown"),
                        final_sev,
                    ],
                )
                db.add(ticket)

                # Persist notification records
                for notif in final_state.get("notification_plan", []):
                    channel = NotificationChannel.SLACK if notif.get("channel") == "slack" else NotificationChannel.EMAIL
                    notification = Notification(
                        incident_id=incident.id,
                        channel=channel,
                        recipient=notif.get("recipient", ""),
                        subject=f"[{final_sev}] {final_state.get('structured_title', title)[:100]}",
                        message=triage_summary or "Incident triaged.",
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
                "assigned_team": assigned_team,
                "ticket_id": linear_issue["identifier"],
                "triage_summary": triage_summary,
            })
            await manager.broadcast({
                "type": "incident_triaged",
                "incident_id": incident_id,
                "severity": final_sev,
                "status": "ticket_created",
            })

        except Exception as e:
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(e))
            logger.error("Pipeline runner failed for %s: %s", incident_id, e, exc_info=True)
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


# ============================================
# Resolution Flow
# ============================================

async def _handle_resolution(
    incident_id: str,
    title: str,
    severity: str,
    reporter_name: str,
    reporter_email: str,
    db: AsyncSession,
    incident: Incident,
):
    """
    Handle resolution notifications when an incident is resolved.
    Updates Linear ticket, sends Slack message, emails the reporter.
    """
    from app.models import Notification, NotificationChannel

    logger.info("✅ Processing resolution for incident %s", incident_id)
    INCIDENTS_RESOLVED.inc()

    with tracer.start_as_current_span("api.handle_resolution") as span:
        span.set_attribute("incident.id", incident_id)
        span.set_attribute("incident.severity", severity)

    # 1. Update Linear ticket to Done
    linear_issue = linear_service.get_issue_by_incident(incident_id)
    if linear_issue:
        linear_service.update_issue(linear_issue["id"], state="done")
        logger.info("📋 Linear ticket %s marked as Done", linear_issue["identifier"])

    # 2. Send Slack resolution notification
    slack_msg = slack_service.format_resolution_message(
        incident_id=incident_id,
        title=title,
        severity=severity,
    )
    # Send to the same channels that were alerted
    for channel_name in ["#critical-incidents", "#incidents"]:
        slack_service.send_message(
            channel=channel_name,
            text=slack_msg["text"],
            blocks=slack_msg["blocks"],
            incident_id=incident_id,
            urgency="resolution",
        )

    # Persist Slack resolution notification
    slack_notif = Notification(
        incident_id=uuid.UUID(incident_id),
        channel=NotificationChannel.SLACK,
        recipient="#critical-incidents",
        subject=f"✅ Resolved: {title[:100]}",
        message=f"Incident {incident_id[:8]} has been resolved.",
        is_sent=True,
        sent_at=datetime.now(timezone.utc),
    )
    db.add(slack_notif)

    # 3. Email the reporter about resolution
    if reporter_email:
        email_content = email_service.format_resolution_email(
            incident_id=incident_id,
            title=title,
            severity=severity,
            reporter_name=reporter_name,
        )
        email_service.send_email(
            to=reporter_email,
            subject=email_content["subject"],
            html_body=email_content["html_body"],
            incident_id=incident_id,
            email_type="resolution",
        )

        # Persist email notification
        email_notif = Notification(
            incident_id=uuid.UUID(incident_id),
            channel=NotificationChannel.EMAIL,
            recipient=reporter_email,
            subject=email_content["subject"],
            message=f"Resolution notification sent to {reporter_name}.",
            is_sent=True,
            sent_at=datetime.now(timezone.utc),
        )
        db.add(email_notif)

    await db.flush()
    logger.info("✅ Resolution notifications sent for incident %s", incident_id)


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

