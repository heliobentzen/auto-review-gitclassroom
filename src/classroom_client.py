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

    def __init__(self, token: str, timeout: int = 30) -> None:
        self.session = requests.Session()
        self.timeout = timeout
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

    def _get_json(self, path: str, *, params: dict | None = None) -> list[dict] | dict:
        resp = self.session.get(
            f"{self.BASE_URL}{path}",
            params=params,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def list_classrooms(self) -> list[dict]:
        """Return all classrooms accessible to the authenticated user."""
        return self._get_json("/classrooms")  # type: ignore[return-value]

    def get_classroom(self, classroom_id: int) -> dict:
        """Return a single classroom by ID."""
        return self._get_json(f"/classrooms/{classroom_id}")  # type: ignore[return-value]

    def list_assignments(self, classroom_id: int) -> list[dict]:
        """Return all assignments for a classroom."""
        return self._get_json(f"/classrooms/{classroom_id}/assignments")  # type: ignore[return-value]

    def get_assignment(self, assignment_id: int) -> dict:
        """Return a single assignment by ID."""
        return self._get_json(f"/assignments/{assignment_id}")  # type: ignore[return-value]

    def list_accepted_assignments(self, assignment_id: int) -> list[dict]:
        """Return all student submissions for an assignment (auto-paginated)."""
        results: list[dict] = []
        page = 1
        while True:
            data = self._get_json(
                f"/assignments/{assignment_id}/accepted_assignments",
                params={"page": page, "per_page": 100},
            )
            if not data:
                break
            results.extend(data)  # type: ignore[arg-type]
            page += 1
        return results
