"""Tests for CodeReviewer."""

from __future__ import annotations

import json

import pytest

from src.reviewer import CodeReviewer


_SAMPLE_REVIEW = {
    "issue_title": "Code Review: improve error handling",
    "issue_body": "## Summary\nGood start.\n## Issues Found\n- No error handling.\n## Suggested Improvements\n- Add try/except.",
    "grade": 7,
    "grade_comment": "Solid work but missing error handling.",
}


@pytest.fixture
def mock_openai(mocker):
    """Patch openai.OpenAI so no real HTTP calls are made."""
    mock_client = mocker.MagicMock()

    # Build a fake chat completion response.
    fake_choice = mocker.MagicMock()
    fake_choice.message.content = json.dumps(_SAMPLE_REVIEW)
    mock_response = mocker.MagicMock()
    mock_response.choices = [fake_choice]
    mock_client.chat.completions.create.return_value = mock_response

    mocker.patch("src.reviewer.OpenAI", return_value=mock_client)
    return mock_client


class TestCodeReviewer:
    def test_review_returns_expected_keys(self, mock_openai):
        reviewer = CodeReviewer(api_key="fake")
        result = reviewer.review(
            "owner/repo",
            {"main.py": "print('hello')"},
            "Lab 1",
        )
        assert "issue_title" in result
        assert "issue_body" in result
        assert "grade" in result
        assert "grade_comment" in result

    def test_review_grade_value(self, mock_openai):
        reviewer = CodeReviewer(api_key="fake")
        result = reviewer.review("owner/repo", {"main.py": "x = 1"})
        assert result["grade"] == 7

    def test_review_passes_assignment_title(self, mock_openai):
        reviewer = CodeReviewer(api_key="fake")
        reviewer.review("owner/repo", {"main.py": "x = 1"}, "My Assignment")
        call_args = mock_openai.chat.completions.create.call_args
        user_content = call_args.kwargs["messages"][1]["content"]
        assert "My Assignment" in user_content

    def test_review_includes_file_content_in_prompt(self, mock_openai):
        reviewer = CodeReviewer(api_key="fake")
        reviewer.review("owner/repo", {"solution.py": "def foo(): pass"})
        call_args = mock_openai.chat.completions.create.call_args
        user_content = call_args.kwargs["messages"][1]["content"]
        assert "solution.py" in user_content
        assert "def foo(): pass" in user_content

    def test_review_uses_specified_model(self, mock_openai):
        reviewer = CodeReviewer(api_key="fake", model="gpt-4o")
        reviewer.review("owner/repo", {"main.py": "pass"})
        call_args = mock_openai.chat.completions.create.call_args
        assert call_args.kwargs["model"] == "gpt-4o"

    def test_review_empty_files(self, mock_openai):
        reviewer = CodeReviewer(api_key="fake")
        result = reviewer.review("owner/repo", {})
        assert result["grade"] == 7  # mocked value still returned

    def test_format_files_truncates_long_content(self):
        long_content = "x" * 10_000
        formatted = CodeReviewer._format_files({"big.py": long_content}, max_chars_per_file=100)
        assert "[truncated]" in formatted
        assert len(formatted) < 10_000

    def test_format_files_empty(self):
        result = CodeReviewer._format_files({})
        assert "(no source files found)" in result

    def test_format_files_includes_path(self):
        result = CodeReviewer._format_files({"path/to/code.py": "print(1)"})
        assert "path/to/code.py" in result
