"""
Trinity — Integrations Module
Singleton instances of mocked external services (Linear, Slack, Email).
"""

from app.integrations.linear_mock import LinearMockService
from app.integrations.slack_mock import SlackMockService
from app.integrations.email_mock import EmailMockService

# Singleton service instances — shared across the application
linear_service = LinearMockService()
slack_service = SlackMockService()
email_service = EmailMockService()

__all__ = [
    "linear_service",
    "slack_service",
    "email_service",
    "LinearMockService",
    "SlackMockService",
    "EmailMockService",
]
