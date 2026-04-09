"""
TriageForge — Mocked Slack Webhook Service
Simulates Slack incoming webhooks with Block Kit message formatting.
Stores channel message history in-memory for the mock inbox UI.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("triageforge.integrations.slack")


# Severity badge emojis
SEVERITY_EMOJI = {
    "P1": "🔴",
    "P2": "🟠",
    "P3": "🟡",
    "P4": "🟢",
}

# Urgency label text
URGENCY_LABELS = {
    "immediate": "⚡ IMMEDIATE — Page oncall",
    "high": "🔔 HIGH — Respond within 15 min",
    "normal": "📬 Normal priority",
    "low": "📋 Low priority — next sprint",
}


class SlackMockService:
    """
    Mocked Slack incoming webhook service.
    Stores messages per channel in-memory for demo display.
    """

    def __init__(self):
        self._channels: dict[str, list[dict]] = {}
        self._message_count: int = 0
        logger.info("💬 Slack Mock Service initialized")

    @property
    def total_messages(self) -> int:
        return self._message_count

    def send_message(
        self,
        channel: str,
        text: str,
        blocks: list[dict] | None = None,
        incident_id: str = "",
        urgency: str = "normal",
    ) -> dict:
        """
        Send a message to a mocked Slack channel.
        Returns a Slack-style message response.
        """
        self._message_count += 1
        now = datetime.now(timezone.utc)
        ts = str(now.timestamp())

        message = {
            "ok": True,
            "channel": channel,
            "ts": ts,
            "message": {
                "text": text,
                "blocks": blocks or [],
                "ts": ts,
                "type": "message",
                "subtype": "bot_message",
                "username": "TriageForge",
                "bot_id": "B_TRIAGEFORGE",
                "icons": {"emoji": ":rotating_light:"},
            },
            "_metadata": {
                "incident_id": incident_id,
                "urgency": urgency,
                "sent_at": now.isoformat(),
                "message_id": str(uuid.uuid4()),
            },
        }

        if channel not in self._channels:
            self._channels[channel] = []
        self._channels[channel].append(message)

        logger.info(
            "💬 Slack: Sent to %s — %s [%s]",
            channel, text[:80], urgency,
        )

        return message

    def format_incident_message(
        self,
        incident_id: str,
        title: str,
        severity: str,
        affected_service: str,
        assigned_team: str,
        triage_summary: str,
        recommended_actions: list[str] | None = None,
        is_duplicate: bool = False,
    ) -> dict:
        """
        Build a Slack Block Kit formatted incident notification.
        Returns {text, blocks} ready for send_message().
        """
        emoji = SEVERITY_EMOJI.get(severity, "⚪")
        fallback_text = f"{emoji} [{severity}] {title}"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} [{severity}] Incident Alert",
                    "emoji": True,
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{title}*",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Severity:*\n{emoji} {severity}"},
                    {"type": "mrkdwn", "text": f"*Service:*\n`{affected_service}`"},
                    {"type": "mrkdwn", "text": f"*Team:*\n{assigned_team}"},
                    {"type": "mrkdwn", "text": f"*Duplicate:*\n{'⚠️ Yes' if is_duplicate else '✅ No'}"},
                ],
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Triage Summary:*\n{triage_summary[:500]}",
                },
            },
        ]

        # Add recommended actions
        if recommended_actions:
            actions_text = "\n".join(f"• {a}" for a in recommended_actions[:5])
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Recommended Actions:*\n{actions_text}",
                },
            })

        # Action buttons
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "🔍 View in TriageForge"},
                    "url": f"http://localhost:3000/incident/{incident_id}",
                    "style": "primary",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✅ Acknowledge"},
                    "value": f"ack_{incident_id}",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "📋 View Ticket"},
                    "url": f"https://linear.app/triageforge/issue/TF-{incident_id[:8].upper()}",
                },
            ],
        })

        # Footer
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"🤖 Triaged by *TriageForge* at {datetime.now(timezone.utc).strftime('%H:%M UTC')} | Incident `{incident_id[:8]}`",
                },
            ],
        })

        return {"text": fallback_text, "blocks": blocks}

    def format_resolution_message(
        self,
        incident_id: str,
        title: str,
        severity: str,
        resolved_by: str = "SRE Team",
    ) -> dict:
        """Build a Slack Block Kit message for incident resolution."""
        text = f"✅ [{severity}] Resolved: {title}"
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"✅ *Incident Resolved*\n\n*{title}*\n\nResolved by: {resolved_by}\nSeverity: {severity}",
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "📊 View Postmortem"},
                        "url": f"http://localhost:3000/incident/{incident_id}",
                    },
                ],
            },
        ]
        return {"text": text, "blocks": blocks}

    def get_channel_history(
        self,
        channel: str,
        limit: int = 50,
    ) -> list[dict]:
        """Get message history for a channel."""
        messages = self._channels.get(channel, [])
        return messages[-limit:]

    def list_channels(self) -> list[dict]:
        """List all channels that have received messages."""
        return [
            {
                "channel": ch,
                "message_count": len(msgs),
                "latest_ts": msgs[-1]["ts"] if msgs else None,
            }
            for ch, msgs in self._channels.items()
        ]

    def get_all_messages(self, limit: int = 100) -> list[dict]:
        """Get all messages across all channels, sorted by time."""
        all_msgs = []
        for msgs in self._channels.values():
            all_msgs.extend(msgs)
        all_msgs.sort(key=lambda m: m["ts"], reverse=True)
        return all_msgs[:limit]
