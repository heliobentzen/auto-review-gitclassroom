"""GitHub Classroom REST API client."""

from __future__ import annotations

import requests


class ClassroomClient:
    """Client for the GitHub Classroom REST API.

    Requires a GitHub personal access token with the ``repo`` and
    ``manage_runners:org`` scopes (or, at minimum, the classic token
    ``repo`` scope so that Classroom endpoints are accessible).
    """

    BASE_URL = "https://api.github.com"

    def __init__(self, token: str) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

    def list_classrooms(self) -> list[dict]:
        """Return all classrooms accessible to the authenticated user."""
        resp = self.session.get(f"{self.BASE_URL}/classrooms")
        resp.raise_for_status()
        return resp.json()

    def get_classroom(self, classroom_id: int) -> dict:
        """Return a single classroom by ID."""
        resp = self.session.get(f"{self.BASE_URL}/classrooms/{classroom_id}")
        resp.raise_for_status()
        return resp.json()

    def list_assignments(self, classroom_id: int) -> list[dict]:
        """Return all assignments for a classroom."""
        resp = self.session.get(
            f"{self.BASE_URL}/classrooms/{classroom_id}/assignments"
        )
        resp.raise_for_status()
        return resp.json()

    def get_assignment(self, assignment_id: int) -> dict:
        """Return a single assignment by ID."""
        resp = self.session.get(f"{self.BASE_URL}/assignments/{assignment_id}")
        resp.raise_for_status()
        return resp.json()

    def list_accepted_assignments(self, assignment_id: int) -> list[dict]:
        """Return all student submissions for an assignment (auto-paginated)."""
        results: list[dict] = []
        page = 1
        while True:
            resp = self.session.get(
                f"{self.BASE_URL}/assignments/{assignment_id}/accepted_assignments",
                params={"page": page, "per_page": 100},
            )
            resp.raise_for_status()
            data: list[dict] = resp.json()
            if not data:
                break
            results.extend(data)
            page += 1
        return results
