"""AI-powered code reviewer using the OpenAI chat completions API."""

from __future__ import annotations

import json

from openai import OpenAI


_REVIEW_SYSTEM_PROMPT = """\
You are an experienced software engineering instructor reviewing student code.
Your task is to provide:
1. A detailed code review identifying essential improvements and code corrections
   (formatted as a GitHub issue body in Markdown).
2. A numeric grade from 0 to 10, where 10 is perfect.
   Consider that the author is a technical-level (vocational/undergraduate) student.
3. A brief comment (1–3 sentences) explaining the grade.

Respond ONLY with a valid JSON object using exactly these keys:
{
  "issue_title": "<short summary suitable for a GitHub issue title>",
  "issue_body": "<full Markdown review with sections: ## Summary, ## Issues Found, ## Suggested Improvements>",
  "grade": <integer or float 0–10>,
  "grade_comment": "<brief explanation of the grade>"
}
"""


class CodeReviewer:
    """Uses OpenAI to review source code and produce structured feedback."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def review(
        self,
        repo_name: str,
        files: dict[str, str],
        assignment_title: str = "",
    ) -> dict:
        """Review code files and return a structured feedback dict.

        Parameters
        ----------
        repo_name:
            The repository name shown to the model for context.
        files:
            Mapping of ``file_path -> content`` to review.
        assignment_title:
            Human-readable assignment name for additional context.

        Returns
        -------
        dict
            Keys: ``issue_title``, ``issue_body``, ``grade``, ``grade_comment``.
        """
        code_block = self._format_files(files)

        user_message = (
            f"Assignment: {assignment_title}\n"
            f"Repository: {repo_name}\n\n"
            f"Code files to review:\n\n{code_block}"
        )

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": _REVIEW_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        return json.loads(content)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_files(
        files: dict[str, str],
        max_chars_per_file: int = 3_000,
    ) -> str:
        """Render files as fenced code blocks for the prompt."""
        if not files:
            return "(no source files found)"

        parts: list[str] = []
        for path, content in files.items():
            truncated = content[:max_chars_per_file]
            if len(content) > max_chars_per_file:
                truncated += "\n... [truncated]"
            parts.append(f"### `{path}`\n```\n{truncated}\n```")

        return "\n\n".join(parts)
