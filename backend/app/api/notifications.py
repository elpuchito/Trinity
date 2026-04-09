"""
TriageForge — Notifications API
REST endpoints for notification history and mocked Slack/Email inboxes.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.database import get_db
from app.models import Notification, NotificationChannel
from app.integrations import slack_service, email_service

router = APIRouter(tags=["notifications"])


# ============================================
# Notification History (from DB)
# ============================================

@router.get("/api/notifications")
async def list_notifications(
    channel: Optional[str] = None,
    incident_id: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List all notification records from the database."""
    query = select(Notification).order_by(desc(Notification.created_at))

    if channel:
        channel_enum = NotificationChannel.SLACK if channel.lower() == "slack" else NotificationChannel.EMAIL
        query = query.where(Notification.channel == channel_enum)

    if incident_id:
        try:
            query = query.where(Notification.incident_id == uuid.UUID(incident_id))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid incident_id format")

    query = query.limit(limit)
    result = await db.execute(query)
    notifications = result.scalars().all()

    return {
        "notifications": [
            {
                "id": str(n.id),
                "incident_id": str(n.incident_id),
                "channel": n.channel.value,
                "recipient": n.recipient,
                "subject": n.subject,
                "message": n.message[:200] if n.message else "",
                "is_sent": n.is_sent,
                "sent_at": n.sent_at.isoformat() if n.sent_at else None,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in notifications
        ],
        "total": len(notifications),
    }


# ============================================
# Mock Slack Endpoints
# ============================================

@router.post("/api/mock/slack/webhook")
async def mock_slack_webhook(payload: dict):
    """
    Receives Slack-formatted webhook payloads.
    Called internally by the pipeline to simulate Slack delivery.
    """
    channel = payload.get("channel", "#general")
    text = payload.get("text", "")
    blocks = payload.get("blocks", [])
    incident_id = payload.get("incident_id", "")
    urgency = payload.get("urgency", "normal")

    result = slack_service.send_message(
        channel=channel,
        text=text,
        blocks=blocks,
        incident_id=incident_id,
        urgency=urgency,
    )

    return result


@router.get("/api/mock/slack/channels")
async def list_slack_channels():
    """List all Slack channels that have received messages."""
    return {
        "channels": slack_service.list_channels(),
        "total_messages": slack_service.total_messages,
    }


@router.get("/api/mock/slack/channels/{channel}")
async def get_slack_channel_history(
    channel: str,
    limit: int = Query(default=50, le=200),
):
    """Get message history for a specific Slack channel."""
    # Channel names come URL-encoded (e.g. %23critical-incidents → #critical-incidents)
    if not channel.startswith("#"):
        channel = f"#{channel}"

    messages = slack_service.get_channel_history(channel, limit=limit)

    return {
        "channel": channel,
        "messages": messages,
        "count": len(messages),
    }


@router.get("/api/mock/slack/messages")
async def get_all_slack_messages(
    limit: int = Query(default=100, le=500),
):
    """Get all Slack messages across all channels."""
    return {
        "messages": slack_service.get_all_messages(limit=limit),
        "total": slack_service.total_messages,
    }


# ============================================
# Mock Email Endpoints
# ============================================

@router.get("/api/mock/email/inbox")
async def get_email_inbox(
    recipient: Optional[str] = None,
    limit: int = Query(default=50, le=200),
):
    """
    Get the mocked email inbox.
    Optionally filter by recipient email address.
    """
    emails = email_service.get_inbox(recipient=recipient, limit=limit)

    return {
        "emails": emails,
        "count": len(emails),
        "total_sent": email_service.total_sent,
    }


@router.get("/api/mock/email/inbox/{recipient}")
async def get_recipient_inbox(
    recipient: str,
    limit: int = Query(default=50, le=200),
):
    """Get all emails sent to a specific recipient."""
    emails = email_service.get_inbox(recipient=recipient, limit=limit)

    return {
        "recipient": recipient,
        "emails": emails,
        "count": len(emails),
    }


@router.get("/api/mock/email/recipients")
async def list_email_recipients():
    """List all recipients that have received emails."""
    return {
        "recipients": email_service.list_recipients(),
        "total_sent": email_service.total_sent,
    }
