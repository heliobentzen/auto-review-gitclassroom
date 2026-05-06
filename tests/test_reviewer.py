"""Tests for CodeReviewer."""

from __future__ import annotations

import json

import pytest
import requests

from src.reviewer import CodeReviewer


_SAMPLE_REVIEW = {
    "issue_title": "Code Review: improve error handling",
    "issue_body": "## Summary\nGood start.\n## Issues Found\n- No error handling.\n## Suggested Improvements\n- Add try/except.",
    "grade": 7,
    "grade_comment": "Solid work but missing error handling.",
}


@pytest.fixture
def mock_ollama(mocker):
    """Patch requests.post so no real HTTP calls are made."""
    mock_response = mocker.MagicMock()
    mock_response.json.return_value = {
        "message": {"content": json.dumps(_SAMPLE_REVIEW)}
    }
    mock_post = mocker.patch("src.reviewer.requests.post", return_value=mock_response)
    return mock_post


class TestCodeReviewer:
    def test_review_returns_expected_keys(self, mock_ollama):
        reviewer = CodeReviewer()
        result = reviewer.review(
            "owner/repo",
            {"main.py": "print('hello')"},
            "Lab 1",
        )
        assert "issue_title" in result
        assert "issue_body" in result
        assert "grade" in result
        assert "grade_comment" in result

    def test_review_grade_value(self, mock_ollama):
        reviewer = CodeReviewer()
        result = reviewer.review("owner/repo", {"main.py": "x = 1"})
        assert result["grade"] == 7

    def test_review_passes_assignment_title(self, mock_ollama):
        reviewer = CodeReviewer()
        reviewer.review("owner/repo", {"main.py": "x = 1"}, "My Assignment")
        call_args = mock_ollama.call_args
        user_content = call_args.kwargs["json"]["messages"][1]["content"]
        assert "My Assignment" in user_content

    def test_review_includes_file_content_in_prompt(self, mock_ollama):
        reviewer = CodeReviewer()
        reviewer.review("owner/repo", {"solution.py": "def foo(): pass"})
        call_args = mock_ollama.call_args
        user_content = call_args.kwargs["json"]["messages"][1]["content"]
        assert "solution.py" in user_content
        assert "def foo(): pass" in user_content

    def test_review_uses_specified_model(self, mock_ollama):
        reviewer = CodeReviewer(model="qwen2.5-coder:7b")
        reviewer.review("owner/repo", {"main.py": "pass"})
        call_args = mock_ollama.call_args
        assert call_args.kwargs["json"]["model"] == "qwen2.5-coder:7b"

    def test_review_empty_files(self, mock_ollama):
        reviewer = CodeReviewer()
        result = reviewer.review("owner/repo", {})
        assert result["grade"] == 7  # mocked value still returned

    def test_review_uses_configured_base_url(self, mock_ollama):
        reviewer = CodeReviewer(base_url="http://ollama.local:11434")
        reviewer.review("owner/repo", {"main.py": "pass"})
        assert mock_ollama.call_args.args[0] == "http://ollama.local:11434/api/chat"

    def test_review_falls_back_to_ollama_generate_when_chat_is_404(self, mocker):
        chat_response = mocker.MagicMock()
        chat_error = requests.HTTPError("404 Not Found")
        chat_error.response = mocker.MagicMock(status_code=404)
        chat_response.raise_for_status.side_effect = chat_error

        generate_response = mocker.MagicMock()
        generate_response.json.return_value = {"response": json.dumps(_SAMPLE_REVIEW)}

        mock_post = mocker.patch(
            "src.reviewer.requests.post",
            side_effect=[chat_response, generate_response],
        )

        reviewer = CodeReviewer(base_url="http://localhost:11434")
        result = reviewer.review("owner/repo", {"main.py": "print('ok')"})

        assert result["grade"] == _SAMPLE_REVIEW["grade"]
        assert mock_post.call_count == 2
        assert mock_post.call_args_list[0].args[0].endswith("/api/chat")
        assert mock_post.call_args_list[1].args[0].endswith("/api/generate")

    def test_review_uses_gemini_provider(self, mocker):
        gemini_response = mocker.MagicMock()
        gemini_response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": json.dumps(_SAMPLE_REVIEW)}],
                    }
                }
            ]
        }
        mock_post = mocker.patch("src.reviewer.requests.post", return_value=gemini_response)

        reviewer = CodeReviewer(
            provider="gemini",
            model="gemini-1.5-flash",
            gemini_api_key="fake-key",
        )
        result = reviewer.review("owner/repo", {"main.py": "print('ok')"})

        assert result["issue_title"] == _SAMPLE_REVIEW["issue_title"]
        assert "generativelanguage.googleapis.com" in mock_post.call_args.args[0]

    def test_review_gemini_requires_api_key(self):
        reviewer = CodeReviewer(provider="gemini", model="gemini-1.5-flash")
        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            reviewer.review("owner/repo", {"main.py": "print('ok')"})

    def test_review_prompt_includes_weighted_rubric(self, mock_ollama):
        reviewer = CodeReviewer()
        reviewer.review(
            "owner/repo",
            {"main.py": "print('ok')"},
            "Atividade 1",
            "Criar um programa que leia dois valores e mostre a soma.",
        )
        call_args = mock_ollama.call_args
        system_content = call_args.kwargs["json"]["messages"][0]["content"]
        user_content = call_args.kwargs["json"]["messages"][1]["content"]

        assert "Estrutura e Sintaxe (30% - 3,0 pts)" in system_content
        assert "Cumprimento dos Requisitos (70% - 7,0 pts)" in system_content
        assert "não geram pontos adicionais" in user_content
        assert "Nível de exigência: nível de ensino médio" in user_content
        assert "desconto proporcional" in system_content
        assert "Liste no máximo 3 problemas principais" in system_content
        assert "priorize os problemas funcionais" in user_content

    def test_review_prompt_accepts_higher_education_expectation(self, mock_ollama):
        reviewer = CodeReviewer()
        reviewer.review(
            "owner/repo",
            {"main.py": "print('ok')"},
            "Atividade 1",
            "Criar um programa que leia dois valores e mostre a soma.",
            "ensino_superior",
        )
        call_args = mock_ollama.call_args
        user_content = call_args.kwargs["json"]["messages"][1]["content"]

        assert "Nível de exigência: nível de ensino superior" in user_content

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
