"""Tests for ClassroomClient."""

from __future__ import annotations

import pytest
import requests

from src.classroom_client import ClassroomClient


@pytest.fixture
def client(requests_mock):
    """Return a ClassroomClient with a mocked session."""
    return ClassroomClient(token="fake-token")


class TestListClassrooms:
    def test_returns_list(self, requests_mock):
        requests_mock.get(
            "https://api.github.com/classrooms",
            json=[{"id": 1, "name": "CS101"}],
        )
        client = ClassroomClient("token")
        result = client.list_classrooms()
        assert result == [{"id": 1, "name": "CS101"}]

    def test_raises_on_http_error(self, requests_mock):
        requests_mock.get(
            "https://api.github.com/classrooms",
            status_code=401,
            json={"message": "Bad credentials"},
        )
        client = ClassroomClient("token")
        with pytest.raises(requests.exceptions.HTTPError):
            client.list_classrooms()


class TestGetClassroom:
    def test_returns_classroom(self, requests_mock):
        requests_mock.get(
            "https://api.github.com/classrooms/42",
            json={"id": 42, "name": "CS101"},
        )
        client = ClassroomClient("token")
        result = client.get_classroom(42)
        assert result["id"] == 42
        assert result["name"] == "CS101"


class TestListAssignments:
    def test_returns_assignments(self, requests_mock):
        requests_mock.get(
            "https://api.github.com/classrooms/1/assignments",
            json=[{"id": 10, "title": "Lab 1"}],
        )
        client = ClassroomClient("token")
        result = client.list_assignments(1)
        assert len(result) == 1
        assert result[0]["title"] == "Lab 1"


class TestGetAssignment:
    def test_returns_assignment(self, requests_mock):
        requests_mock.get(
            "https://api.github.com/assignments/10",
            json={"id": 10, "title": "Lab 1"},
        )
        client = ClassroomClient("token")
        result = client.get_assignment(10)
        assert result["title"] == "Lab 1"


class TestListAcceptedAssignments:
    def test_returns_all_pages(self, requests_mock):
        page1 = [{"id": 1}, {"id": 2}]
        page2 = [{"id": 3}]

        def response_callback(request, context):
            page = int(request.qs.get("page", ["1"])[0])
            return page1 if page == 1 else (page2 if page == 2 else [])

        requests_mock.get(
            "https://api.github.com/assignments/10/accepted_assignments",
            json=response_callback,
        )
        client = ClassroomClient("token")
        result = client.list_accepted_assignments(10)
        assert len(result) == 3

    def test_returns_empty_when_no_submissions(self, requests_mock):
        requests_mock.get(
            "https://api.github.com/assignments/10/accepted_assignments",
            json=[],
        )
        client = ClassroomClient("token")
        result = client.list_accepted_assignments(10)
        assert result == []

    def test_auth_header_sent(self, requests_mock):
        requests_mock.get(
            "https://api.github.com/assignments/5/accepted_assignments",
            json=[],
        )
        client = ClassroomClient("my-secret-token")
        client.list_accepted_assignments(5)
        assert "Bearer my-secret-token" in requests_mock.last_request.headers.get(
            "Authorization", ""
        )
