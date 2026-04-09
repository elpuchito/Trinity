"""
Trinity — Tickets API
REST endpoints for ticket CRUD and mocked Linear webhook.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Ticket, TicketStatus, Incident
from app.integrations import linear_service

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


# ============================================
# Ticket CRUD Endpoints
# ============================================

@router.get("")
async def list_tickets(
    status: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List all tickets from both DB and the mocked Linear service."""
    # Get in-memory Linear issues
    linear_issues = linear_service.list_issues(state=status, limit=limit)

    # Also get DB tickets for persistence
    query = select(Ticket).order_by(desc(Ticket.created_at)).limit(limit)
    if status:
        status_map = {
            "open": TicketStatus.OPEN,
            "in_progress": TicketStatus.IN_PROGRESS,
            "resolved": TicketStatus.RESOLVED,
            "closed": TicketStatus.CLOSED,
        }
        db_status = status_map.get(status.lower())
        if db_status:
            query = query.where(Ticket.status == db_status)

    result = await db.execute(query)
    db_tickets = result.scalars().all()

    return {
        "linear_issues": linear_issues,
        "db_tickets": [
            {
                "id": str(t.id),
                "external_id": t.external_id,
                "external_url": t.external_url,
                "title": t.title,
                "status": t.status.value,
                "priority": t.priority,
                "assignee": t.assignee,
                "labels": t.labels,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in db_tickets
        ],
        "total_linear": linear_service.issue_count,
        "total_db": len(db_tickets),
    }


@router.get("/{ticket_id}")
async def get_ticket(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a single ticket by ID. Checks Linear mock first, then DB."""
    # Try Linear mock service
    linear_issue = linear_service.get_issue(ticket_id)
    if linear_issue:
        return {"source": "linear", "issue": linear_issue}

    # Try DB by external_id (e.g. TF-1)
    result = await db.execute(
        select(Ticket).where(Ticket.external_id == ticket_id)
    )
    db_ticket = result.scalar_one_or_none()
    if db_ticket:
        return {
            "source": "database",
            "ticket": {
                "id": str(db_ticket.id),
                "external_id": db_ticket.external_id,
                "external_url": db_ticket.external_url,
                "title": db_ticket.title,
                "status": db_ticket.status.value,
                "priority": db_ticket.priority,
                "assignee": db_ticket.assignee,
                "labels": db_ticket.labels,
                "created_at": db_ticket.created_at.isoformat() if db_ticket.created_at else None,
            },
        }

    # Try DB by UUID
    try:
        ticket_uuid = uuid.UUID(ticket_id)
        result = await db.execute(
            select(Ticket).where(Ticket.id == ticket_uuid)
        )
        db_ticket = result.scalar_one_or_none()
        if db_ticket:
            return {
                "source": "database",
                "ticket": {
                    "id": str(db_ticket.id),
                    "external_id": db_ticket.external_id,
                    "external_url": db_ticket.external_url,
                    "title": db_ticket.title,
                    "status": db_ticket.status.value,
                    "priority": db_ticket.priority,
                    "assignee": db_ticket.assignee,
                    "labels": db_ticket.labels,
                    "created_at": db_ticket.created_at.isoformat() if db_ticket.created_at else None,
                },
            }
    except ValueError:
        pass

    raise HTTPException(status_code=404, detail="Ticket not found")


@router.patch("/{ticket_id}")
async def update_ticket(
    ticket_id: str,
    update: dict,
    db: AsyncSession = Depends(get_db),
):
    """
    Update a ticket's status. Updates both Linear mock and DB.
    Body: { "status": "in_progress" | "resolved" | "closed", "assignee": "..." }
    """
    # Map frontend status to Linear workflow state
    status_to_state = {
        "open": "todo",
        "in_progress": "in_progress",
        "resolved": "done",
        "closed": "canceled",
    }

    new_status = update.get("status")
    new_assignee = update.get("assignee")
    linear_state = status_to_state.get(new_status) if new_status else None

    # Update Linear mock
    linear_issue = linear_service.update_issue(
        issue_id=ticket_id,
        state=linear_state,
        assignee=new_assignee,
    )

    # Also update DB ticket
    result = await db.execute(
        select(Ticket).where(Ticket.external_id == ticket_id)
    )
    db_ticket = result.scalar_one_or_none()

    if db_ticket and new_status:
        db_status_map = {
            "open": TicketStatus.OPEN,
            "in_progress": TicketStatus.IN_PROGRESS,
            "resolved": TicketStatus.RESOLVED,
            "closed": TicketStatus.CLOSED,
        }
        db_status = db_status_map.get(new_status)
        if db_status:
            db_ticket.status = db_status
        if new_assignee:
            db_ticket.assignee = new_assignee
        await db.flush()

    if not linear_issue and not db_ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    return {
        "updated": True,
        "linear_issue": linear_issue,
        "db_updated": db_ticket is not None,
    }


# ============================================
# Mock Linear Webhook (inbound status sync)
# ============================================

@router.post("/mock/linear/webhook")
async def mock_linear_webhook(payload: dict):
    """
    Simulate an inbound Linear webhook for status change events.
    In production, Linear would call this when a ticket status changes.
    """
    action = payload.get("action", "")
    issue_data = payload.get("data", {})
    issue_id = issue_data.get("id", "")

    if action == "update" and issue_id:
        state = issue_data.get("state", {}).get("name", "").lower()
        state_map = {"todo": "todo", "in progress": "in_progress", "done": "done", "canceled": "canceled"}
        linear_state = state_map.get(state)

        if linear_state:
            updated = linear_service.update_issue(issue_id, state=linear_state)
            return {"ok": True, "updated": updated is not None}

    return {"ok": True, "action": "ignored"}
