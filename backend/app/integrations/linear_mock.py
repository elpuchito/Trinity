"""
Trinity — Mocked Linear API Service
Simulates the Linear issue tracking API for hackathon demo.
Provides realistic ticket CRUD with in-memory state + DB persistence.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("triageforge.integrations.linear")


# Priority mapping: P1-P4 → Linear priority levels (1=urgent, 4=low)
PRIORITY_MAP = {
    "P1": {"priority": 1, "label": "Urgent"},
    "P2": {"priority": 2, "label": "High"},
    "P3": {"priority": 3, "label": "Medium"},
    "P4": {"priority": 4, "label": "Low"},
}

# Linear-style workflow states
WORKFLOW_STATES = {
    "triage": {"id": "state-triage", "name": "Triage", "color": "#bec2c8", "type": "triage"},
    "backlog": {"id": "state-backlog", "name": "Backlog", "color": "#e2e2e2", "type": "backlog"},
    "todo": {"id": "state-todo", "name": "Todo", "color": "#e2e2e2", "type": "unstarted"},
    "in_progress": {"id": "state-progress", "name": "In Progress", "color": "#f2c94c", "type": "started"},
    "done": {"id": "state-done", "name": "Done", "color": "#5e6ad2", "type": "completed"},
    "canceled": {"id": "state-canceled", "name": "Canceled", "color": "#95a2b3", "type": "canceled"},
}


class LinearMockService:
    """
    Mocked Linear ticketing API.
    Stores issues in-memory with realistic Linear-style responses.
    """

    def __init__(self):
        self._issues: dict[str, dict] = {}
        self._counter: int = 0
        self._team_key = "TF"
        logger.info("📋 Linear Mock Service initialized")

    @property
    def issue_count(self) -> int:
        return len(self._issues)

    def create_issue(
        self,
        title: str,
        description: str = "",
        priority: str = "P3",
        assignee: str = "",
        labels: list[str] | None = None,
        incident_id: str = "",
    ) -> dict:
        """
        Create a new issue (ticket) in the mocked Linear workspace.
        Returns a Linear-style issue object.
        """
        self._counter += 1
        issue_number = self._counter
        identifier = f"{self._team_key}-{issue_number}"
        issue_id = str(uuid.uuid4())

        priority_info = PRIORITY_MAP.get(priority, PRIORITY_MAP["P3"])
        now = datetime.now(timezone.utc).isoformat()

        issue = {
            "id": issue_id,
            "identifier": identifier,
            "number": issue_number,
            "title": title,
            "description": description,
            "priority": priority_info["priority"],
            "priorityLabel": priority_info["label"],
            "state": WORKFLOW_STATES["todo"].copy(),
            "assignee": {
                "id": str(uuid.uuid4()),
                "name": assignee or "Unassigned",
                "email": f"{(assignee or 'unassigned').lower().replace(' ', '.')}@saleor-demo.com",
            } if assignee else None,
            "team": {
                "id": "team-triageforge",
                "name": assignee or "SRE On-Call",
                "key": self._team_key,
            },
            "labels": [
                {"id": str(uuid.uuid4()), "name": label, "color": "#5e6ad2"}
                for label in (labels or [])
            ],
            "url": f"https://linear.app/triageforge/issue/{identifier}",
            "createdAt": now,
            "updatedAt": now,
            "completedAt": None,
            "canceledAt": None,
            "incident_id": incident_id,
            "_metadata": {
                "source": "triageforge-pipeline",
                "created_via": "api",
            },
        }

        self._issues[issue_id] = issue

        logger.info(
            "📋 Linear: Created issue %s — %s [%s] → %s",
            identifier, title[:60], priority, assignee or "unassigned",
        )

        return issue

    def update_issue(
        self,
        issue_id: str,
        state: Optional[str] = None,
        priority: Optional[str] = None,
        assignee: Optional[str] = None,
        title: Optional[str] = None,
    ) -> dict | None:
        """Update an existing issue. Returns updated issue or None if not found."""
        issue = self._issues.get(issue_id)
        if not issue:
            # Try finding by identifier
            issue = next(
                (i for i in self._issues.values() if i["identifier"] == issue_id),
                None,
            )
        if not issue:
            logger.warning("Linear: Issue %s not found", issue_id)
            return None

        now = datetime.now(timezone.utc).isoformat()

        if state and state in WORKFLOW_STATES:
            issue["state"] = WORKFLOW_STATES[state].copy()
            if state == "done":
                issue["completedAt"] = now
            elif state == "canceled":
                issue["canceledAt"] = now

        if priority and priority in PRIORITY_MAP:
            p = PRIORITY_MAP[priority]
            issue["priority"] = p["priority"]
            issue["priorityLabel"] = p["label"]

        if assignee is not None:
            issue["assignee"] = {
                "id": str(uuid.uuid4()),
                "name": assignee,
                "email": f"{assignee.lower().replace(' ', '.')}@saleor-demo.com",
            }

        if title:
            issue["title"] = title

        issue["updatedAt"] = now

        logger.info(
            "📋 Linear: Updated %s — state=%s",
            issue["identifier"], issue["state"]["name"],
        )

        return issue

    def get_issue(self, issue_id: str) -> dict | None:
        """Get a single issue by ID or identifier."""
        issue = self._issues.get(issue_id)
        if not issue:
            issue = next(
                (i for i in self._issues.values() if i["identifier"] == issue_id),
                None,
            )
        return issue

    def list_issues(
        self,
        state: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """List all issues, optionally filtered by state."""
        issues = list(self._issues.values())

        if state:
            issues = [i for i in issues if i["state"]["name"].lower() == state.lower()]

        # Sort by creation time, newest first
        issues.sort(key=lambda i: i["createdAt"], reverse=True)

        return issues[:limit]

    def get_issue_by_incident(self, incident_id: str) -> dict | None:
        """Find issue linked to a specific incident."""
        return next(
            (i for i in self._issues.values() if i.get("incident_id") == incident_id),
            None,
        )
