"""Integration-style tests for the main CLI orchestration."""

from __future__ import annotations

import json

import pytest

from src.main import main


# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------

_FAKE_ASSIGNMENT = {"id": 10, "title": "Lab 1"}
_FAKE_SUBMISSIONS = [
    {
        "repository": {"full_name": "org/student1-repo"},
        "students": [{"login": "student1"}],
    },
    {
        "repository": {"full_name": "org/student2-repo"},
        "students": [{"login": "student2"}],
    },
]
_FAKE_REVIEW = {
    "issue_title": "Code Review Feedback",
    "issue_body": "## Summary\nGood work.",
    "grade": 8,
    "grade_comment": "Solid submission.",
}


@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "fake-github-token")
    monkeypatch.setenv("OPENAI_API_KEY", "fake-openai-key")


@pytest.fixture
def mock_classroom(mocker):
    m = mocker.MagicMock()
    m.get_assignment.return_value = _FAKE_ASSIGNMENT
    m.list_accepted_assignments.return_value = _FAKE_SUBMISSIONS
    mocker.patch("src.main.ClassroomClient", return_value=m)
    return m


@pytest.fixture
def mock_github(mocker):
    m = mocker.MagicMock()
    m.get_repo_files.return_value = {"main.py": "print('hello')"}
    m.create_issue.return_value = "https://github.com/org/student1-repo/issues/1"
    mocker.patch("src.main.GitHubClient", return_value=m)
    return m


@pytest.fixture
def mock_reviewer(mocker):
    m = mocker.MagicMock()
    m.review.return_value = _FAKE_REVIEW
    mocker.patch("src.main.CodeReviewer", return_value=m)
    return m


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMainCLI:
    def test_missing_github_token_exits(self, monkeypatch, mocker):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "key")
        mocker.patch("src.main.load_dotenv")
        with pytest.raises(SystemExit) as exc_info:
            main(["--assignment-id", "10"])
        assert exc_info.value.code == 1

    def test_missing_openai_key_exits(self, monkeypatch, mocker):
        monkeypatch.setenv("GITHUB_TOKEN", "token")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        mocker.patch("src.main.load_dotenv")
        with pytest.raises(SystemExit) as exc_info:
            main(["--assignment-id", "10"])
        assert exc_info.value.code == 1

    def test_dry_run_skips_issue_creation(
        self,
        mock_env,
        mock_classroom,
        mock_github,
        mock_reviewer,
        mocker,
        tmp_path,
    ):
        mocker.patch("src.main.load_dotenv")
        output = str(tmp_path / "report.csv")
        main(["--assignment-id", "10", "--dry-run", "--output", output])
        mock_github.create_issue.assert_not_called()

    def test_issues_created_for_each_student(
        self,
        mock_env,
        mock_classroom,
        mock_github,
        mock_reviewer,
        mocker,
        tmp_path,
    ):
        mocker.patch("src.main.load_dotenv")
        output = str(tmp_path / "report.csv")
        main(["--assignment-id", "10", "--output", output])
        assert mock_github.create_issue.call_count == len(_FAKE_SUBMISSIONS)

    def test_csv_report_is_exported(
        self,
        mock_env,
        mock_classroom,
        mock_github,
        mock_reviewer,
        mocker,
        tmp_path,
    ):
        import csv
        import os

        mocker.patch("src.main.load_dotenv")
        output = str(tmp_path / "report.csv")
        main(["--assignment-id", "10", "--output", output])
        assert os.path.exists(output)
        with open(output, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        assert len(rows) == len(_FAKE_SUBMISSIONS)
        assert rows[0]["student"] == "student1"
        assert float(rows[0]["grade"]) == 8.0

    def test_empty_submissions_exits_cleanly(
        self,
        mock_env,
        mock_classroom,
        mock_github,
        mock_reviewer,
        mocker,
    ):
        mocker.patch("src.main.load_dotenv")
        mock_classroom.list_accepted_assignments.return_value = []
        with pytest.raises(SystemExit) as exc_info:
            main(["--assignment-id", "10"])
        assert exc_info.value.code == 0

    def test_error_in_review_is_recorded(
        self,
        mock_env,
        mock_classroom,
        mock_github,
        mock_reviewer,
        mocker,
        tmp_path,
    ):
        import csv

        mocker.patch("src.main.load_dotenv")
        mock_reviewer.review.side_effect = RuntimeError("API down")
        output = str(tmp_path / "report.csv")
        main(["--assignment-id", "10", "--output", output])
        with open(output, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        for row in rows:
            assert row["grade"] == "0"
            assert "Error" in row["grade_comment"]
