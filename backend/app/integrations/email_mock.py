"""
Trinity — Mocked Email SMTP Service
Simulates email sending with rich HTML templates.
Stores emails in-memory for the mock inbox viewer.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("triageforge.integrations.email")


# Severity colors for HTML emails
SEVERITY_COLORS = {
    "P1": "#FF3366",
    "P2": "#FFB800",
    "P3": "#00F0FF",
    "P4": "#00FF94",
}


class EmailMockService:
    """
    Mocked email SMTP service.
    Generates realistic HTML emails and stores them in-memory.
    """

    def __init__(self):
        self._inbox: list[dict] = {}  # recipient → [emails]
        self._all_emails: list[dict] = []
        self._send_count: int = 0
        self._inbox: dict[str, list[dict]] = {}
        logger.info("📧 Email Mock Service initialized")

    @property
    def total_sent(self) -> int:
        return self._send_count

    def send_email(
        self,
        to: str,
        subject: str,
        html_body: str,
        from_addr: str = "triageforge@saleor-demo.com",
        incident_id: str = "",
        email_type: str = "alert",
    ) -> dict:
        """
        Send a mocked email. Stores it in-memory and returns SMTP-style response.
        """
        self._send_count += 1
        now = datetime.now(timezone.utc)
        message_id = f"<{uuid.uuid4()}@triageforge.local>"

        email = {
            "message_id": message_id,
            "from": from_addr,
            "to": to,
            "subject": subject,
            "html_body": html_body,
            "text_body": _strip_html(html_body),
            "sent_at": now.isoformat(),
            "email_type": email_type,
            "incident_id": incident_id,
            "headers": {
                "X-Trinity-Incident": incident_id,
                "X-Trinity-Type": email_type,
                "X-Priority": "1" if "P1" in subject else "3",
                "Content-Type": "text/html; charset=utf-8",
            },
            "_smtp_response": {
                "status": 250,
                "message": f"2.0.0 Ok: queued as {uuid.uuid4().hex[:12]}",
            },
        }

        # Store in recipient inbox
        if to not in self._inbox:
            self._inbox[to] = []
        self._inbox[to].append(email)
        self._all_emails.append(email)

        logger.info(
            "📧 Email: Sent to %s — \"%s\" [%s]",
            to, subject[:60], email_type,
        )

        return email

    def format_oncall_alert(
        self,
        incident_id: str,
        title: str,
        severity: str,
        affected_service: str,
        assigned_team: str,
        triage_summary: str,
        runbook_steps: str = "",
        recommended_actions: list[str] | None = None,
    ) -> dict:
        """
        Build an HTML email for oncall engineers.
        Returns {subject, html_body}.
        """
        color = SEVERITY_COLORS.get(severity, "#00F0FF")
        actions_html = ""
        if recommended_actions:
            actions_html = "<ol>" + "".join(f"<li>{a}</li>" for a in recommended_actions) + "</ol>"

        runbook_html = ""
        if runbook_steps:
            runbook_html = f"""
            <div style="background: #1a1a2e; border-left: 3px solid {color}; padding: 16px; margin: 16px 0; border-radius: 4px;">
                <h3 style="color: {color}; margin-top: 0;">📋 Suggested Runbook</h3>
                <pre style="color: #e0e0e0; white-space: pre-wrap; font-family: 'JetBrains Mono', monospace; font-size: 13px;">{runbook_steps[:1000]}</pre>
            </div>
            """

        subject = f"[{severity}] {title}"
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"></head>
        <body style="margin: 0; padding: 0; background: #0A0E1A; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;">
            <div style="max-width: 600px; margin: 0 auto; padding: 32px 24px;">
                <!-- Header -->
                <div style="background: linear-gradient(135deg, #0A0E1A 0%, #1a1a3e 100%); border: 1px solid {color}40; border-radius: 12px; padding: 24px; margin-bottom: 24px;">
                    <div style="font-size: 12px; color: {color}; text-transform: uppercase; letter-spacing: 2px; margin-bottom: 8px;">⚡ Trinity Alert</div>
                    <h1 style="color: #ffffff; margin: 0; font-size: 22px; line-height: 1.3;">{title}</h1>
                    <div style="margin-top: 16px; display: flex; gap: 12px;">
                        <span style="background: {color}20; color: {color}; padding: 4px 12px; border-radius: 20px; font-size: 13px; font-weight: 600;">{severity}</span>
                        <span style="background: #ffffff10; color: #a0a0a0; padding: 4px 12px; border-radius: 20px; font-size: 13px;">{affected_service}</span>
                        <span style="background: #ffffff10; color: #a0a0a0; padding: 4px 12px; border-radius: 20px; font-size: 13px;">{assigned_team}</span>
                    </div>
                </div>

                <!-- Triage Summary -->
                <div style="background: #12152B; border: 1px solid #ffffff10; border-radius: 12px; padding: 24px; margin-bottom: 24px;">
                    <h2 style="color: #ffffff; font-size: 16px; margin-top: 0;">🔍 Triage Summary</h2>
                    <p style="color: #c0c0c0; line-height: 1.6; font-size: 14px;">{triage_summary}</p>
                </div>

                <!-- Recommended Actions -->
                {"" if not actions_html else f'''
                <div style="background: #12152B; border: 1px solid #ffffff10; border-radius: 12px; padding: 24px; margin-bottom: 24px;">
                    <h2 style="color: #ffffff; font-size: 16px; margin-top: 0;">🎯 Recommended Actions</h2>
                    <div style="color: #c0c0c0; line-height: 1.8; font-size: 14px;">{actions_html}</div>
                </div>
                '''}

                <!-- Runbook -->
                {runbook_html}

                <!-- CTA -->
                <div style="text-align: center; margin: 32px 0;">
                    <a href="http://localhost:3000/incident/{incident_id}"
                       style="background: {color}; color: #0A0E1A; padding: 14px 32px; border-radius: 8px; text-decoration: none; font-weight: 700; font-size: 14px; display: inline-block;">
                        View in Trinity →
                    </a>
                </div>

                <!-- Footer -->
                <div style="text-align: center; color: #666; font-size: 12px; margin-top: 32px; padding-top: 16px; border-top: 1px solid #ffffff0a;">
                    🤖 Auto-triaged by Trinity | Incident {incident_id[:8]}
                </div>
            </div>
        </body>
        </html>
        """

        return {"subject": subject, "html_body": html_body}

    def format_reporter_confirmation(
        self,
        incident_id: str,
        title: str,
        severity: str,
        reporter_name: str,
        ticket_id: str = "",
    ) -> dict:
        """
        Build an HTML confirmation email for the incident reporter.
        Returns {subject, html_body}.
        """
        color = SEVERITY_COLORS.get(severity, "#00F0FF")
        subject = f"Incident received: {title}"
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"></head>
        <body style="margin: 0; padding: 0; background: #0A0E1A; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;">
            <div style="max-width: 600px; margin: 0 auto; padding: 32px 24px;">
                <div style="background: linear-gradient(135deg, #0A0E1A 0%, #1a1a3e 100%); border: 1px solid {color}40; border-radius: 12px; padding: 32px;">
                    <div style="font-size: 12px; color: {color}; text-transform: uppercase; letter-spacing: 2px; margin-bottom: 8px;">Trinity</div>
                    <h1 style="color: #ffffff; margin: 0 0 16px 0; font-size: 22px;">Hi {reporter_name},</h1>
                    <p style="color: #c0c0c0; line-height: 1.6; font-size: 15px;">
                        Your incident report has been received and automatically triaged by our AI system.
                    </p>
                    <div style="background: #ffffff08; border-radius: 8px; padding: 16px; margin: 20px 0;">
                        <p style="color: #ffffff; margin: 0 0 8px 0; font-weight: 600;">{title}</p>
                        <p style="color: #a0a0a0; margin: 0; font-size: 13px;">
                            Severity: <span style="color: {color}; font-weight: 600;">{severity}</span>
                            {f' | Ticket: <span style="color: {color};">{ticket_id}</span>' if ticket_id else ''}
                        </p>
                    </div>
                    <p style="color: #c0c0c0; line-height: 1.6; font-size: 14px;">
                        The incident has been assigned to the appropriate team and you'll be notified of any updates.
                    </p>
                    <div style="text-align: center; margin-top: 24px;">
                        <a href="http://localhost:3000/incident/{incident_id}"
                           style="background: {color}; color: #0A0E1A; padding: 12px 28px; border-radius: 8px; text-decoration: none; font-weight: 700; font-size: 14px;">
                            Track Your Incident →
                        </a>
                    </div>
                </div>
                <div style="text-align: center; color: #666; font-size: 12px; margin-top: 24px;">
                    🤖 Trinity — Intelligent SRE Incident Triage
                </div>
            </div>
        </body>
        </html>
        """
        return {"subject": subject, "html_body": html_body}

    def format_resolution_email(
        self,
        incident_id: str,
        title: str,
        severity: str,
        reporter_name: str,
        resolved_by: str = "SRE Team",
    ) -> dict:
        """Build an HTML resolution notification email for the reporter."""
        color = "#00FF94"  # Success green
        subject = f"✅ Resolved: {title}"
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"></head>
        <body style="margin: 0; padding: 0; background: #0A0E1A; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;">
            <div style="max-width: 600px; margin: 0 auto; padding: 32px 24px;">
                <div style="background: linear-gradient(135deg, #0A0E1A 0%, #0a2e1a 100%); border: 1px solid {color}40; border-radius: 12px; padding: 32px;">
                    <div style="font-size: 48px; text-align: center; margin-bottom: 16px;">✅</div>
                    <h1 style="color: #ffffff; margin: 0 0 16px 0; font-size: 22px; text-align: center;">Incident Resolved</h1>
                    <p style="color: #c0c0c0; line-height: 1.6; font-size: 15px; text-align: center;">
                        Hi {reporter_name}, the incident you reported has been resolved.
                    </p>
                    <div style="background: #ffffff08; border-radius: 8px; padding: 16px; margin: 20px 0;">
                        <p style="color: #ffffff; margin: 0 0 8px 0; font-weight: 600;">{title}</p>
                        <p style="color: #a0a0a0; margin: 0; font-size: 13px;">
                            Resolved by: {resolved_by} | Original severity: {severity}
                        </p>
                    </div>
                    <div style="text-align: center; margin-top: 24px;">
                        <a href="http://localhost:3000/incident/{incident_id}"
                           style="background: {color}; color: #0A0E1A; padding: 12px 28px; border-radius: 8px; text-decoration: none; font-weight: 700; font-size: 14px;">
                            View Details →
                        </a>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        return {"subject": subject, "html_body": html_body}

    def get_inbox(self, recipient: Optional[str] = None, limit: int = 50) -> list[dict]:
        """Get emails for a specific recipient, or all emails."""
        if recipient:
            return self._inbox.get(recipient, [])[-limit:]
        return self._all_emails[-limit:]

    def list_recipients(self) -> list[dict]:
        """List all recipients that have received emails."""
        return [
            {
                "recipient": addr,
                "email_count": len(emails),
                "latest": emails[-1]["sent_at"] if emails else None,
            }
            for addr, emails in self._inbox.items()
        ]


def _strip_html(html: str) -> str:
    """Naive HTML tag stripping for text_body fallback."""
    import re
    text = re.sub(r"<[^>]+>", "", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text
