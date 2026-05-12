"""GitHub Classroom REST API client."""

from __future__ import annotations

import logging
import time

import requests

logger = logging.getLogger(__name__)


class ClassroomClient:
    """Client for the GitHub Classroom REST API.

    Requires a GitHub personal access token with the ``repo`` and
    ``manage_runners:org`` scopes (or, at minimum, the classic token
    ``repo`` scope so that Classroom endpoints are accessible).
    """

    BASE_URL = "https://api.github.com"
    _MAX_RETRIES = 3
    _RETRY_BASE_DELAY = 2  # seconds
    _RETRYABLE_STATUS_CODES = {429, 500, 502, 503}

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
        url = f"{self.BASE_URL}{path}"
        last_exc: Exception | None = None

        for attempt in range(1, self._MAX_RETRIES + 1):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                last_exc = exc
                logger.warning(
                    "GitHub request failed (attempt %d/%d, url=%s): %s",
                    attempt, self._MAX_RETRIES, url, exc,
                )
                if attempt < self._MAX_RETRIES:
                    time.sleep(self._RETRY_BASE_DELAY * (2 ** (attempt - 1)))
                continue

            if resp.status_code in self._RETRYABLE_STATUS_CODES:
                delay = self._RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "GitHub retornou %d (attempt %d/%d, url=%s). "
                    "Aguardando %ds...",
                    resp.status_code, attempt, self._MAX_RETRIES, url, delay,
                )
                if attempt < self._MAX_RETRIES:
                    time.sleep(delay)
                    continue

            resp.raise_for_status()
            return resp.json()

        # Esgotou retries por erro de conexão.
        raise requests.ConnectionError(
            f"GitHub API indisponível após {self._MAX_RETRIES} tentativas: {last_exc}"
        ) from last_exc

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
