"""CLI entry point for auto-review-gitclassroom.

Usage
-----
    python -m src.main --assignment-id <ID> [options]

Required environment variables (or .env file):
    GITHUB_TOKEN   — GitHub personal access token (repo + classroom scopes)

Optional environment variables:
    OLLAMA_HOST    — Ollama server URL (default: http://localhost:11434)
    OLLAMA_MODEL   — Ollama model name (default: qwen2.5-coder:7b)
"""

from __future__ import annotations

import argparse
import difflib
import os
import re
import sys

from dotenv import load_dotenv

from .classroom_client import ClassroomClient
from .config import AppConfig
from .github_client import GitHubClient
from .reporter import GradeReporter
from .reviewer import CodeReviewer


def _log(message: str) -> None:
    """Print progress messages immediately so long runs stay visible."""
    print(message, flush=True)


def _log_error(message: str) -> None:
    """Print error messages immediately to stderr."""
    print(message, file=sys.stderr, flush=True)


def _slugify(value: str) -> str:
    """Return a URL-like slug for loose matching against Classroom links."""
    normalized = []
    for ch in value.lower():
        if "a" <= ch <= "z" or "0" <= ch <= "9":
            normalized.append(ch)
        else:
            normalized.append("-")
    slug = "".join(normalized)
    return re.sub(r"-+", "-", slug).strip("-")


def _slug_key(value: str) -> str:
    """Return a compact slug key used for resilient comparisons."""
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _similarity(left: str, right: str) -> float:
    """Return fuzzy similarity score for two slug-like values."""
    return difflib.SequenceMatcher(None, _slug_key(left), _slug_key(right)).ratio()


def _classroom_candidates(classroom: dict) -> tuple[int | None, list[str]]:
    """Return classroom id and candidate slugs extracted from API payload."""
    classroom_id = classroom.get("id")
    name_slug = _slugify(classroom.get("name", ""))
    api_slug = str(classroom.get("slug", "")).lower()
    return classroom_id, [name_slug, api_slug]


def _submission_identity(submission: dict) -> tuple[str, str]:
    """Return repository full name and best-effort student login."""
    repo_info = submission.get("repository", {})
    repo_full_name: str = repo_info.get("full_name", "")
    students: list[dict] = submission.get("students", [])
    student_login: str = (
        students[0]["login"] if students else repo_full_name.split("/")[-1]
    )
    return repo_full_name, student_login


def _resolve_classroom_id(classroom_ref: str, classroom_client: ClassroomClient) -> int:
    """Resolve the API classroom ID from numeric/classroom-slug URL segment."""
    numeric_match = re.match(r"^(\d+)", classroom_ref)
    slug_hint = classroom_ref.lower().split("-", 1)[1] if "-" in classroom_ref else ""

    if numeric_match:
        candidate_id = int(numeric_match.group(1))
        try:
            classroom_client.get_classroom(candidate_id)
            return candidate_id
        except Exception:
            # Fallback below: some Classroom URLs include a number that is not the API ID.
            pass

    classrooms = classroom_client.list_classrooms()

    for classroom in classrooms:
        classroom_id, candidates = _classroom_candidates(classroom)

        for candidate in candidates:
            if not candidate or classroom_id is None:
                continue
            if slug_hint and slug_hint == candidate:
                return int(classroom_id)

    for classroom in classrooms:
        classroom_id, candidates = _classroom_candidates(classroom)

        for candidate in candidates:
            if not candidate or classroom_id is None:
                continue
            ratio = _similarity(slug_hint, candidate)
            if ratio >= 0.9:
                return int(classroom_id)

    raise ValueError(
        "Could not resolve classroom from URL. Confirm token access and classroom membership."
    )


def _resolve_assignment_id(raw_value: str, classroom_client: ClassroomClient) -> int:
    """Resolve numeric assignment ID from either ID text or Classroom URL."""
    if raw_value.isdigit():
        return int(raw_value)

    url_match = re.search(
        r"classroom\.github\.com/classrooms/([^/]+)/assignments/([^/?#]+)",
        raw_value,
        flags=re.IGNORECASE,
    )
    if not url_match:
        raise ValueError(
            "Invalid --assignment-id. Use a numeric ID or a GitHub Classroom assignment URL."
        )

    classroom_ref = url_match.group(1).strip().lower()
    classroom_id = _resolve_classroom_id(classroom_ref, classroom_client)
    assignment_slug = url_match.group(2).strip().lower()

    if assignment_slug.isdigit():
        return int(assignment_slug)

    assignments = classroom_client.list_assignments(classroom_id)

    for assignment in assignments:
        assignment_id = assignment.get("id")
        title = assignment.get("title", "")
        slug = assignment.get("slug", "")
        title_slug = _slugify(title)
        candidate_slugs = [str(slug).lower(), title_slug]

        if assignment_slug in candidate_slugs and assignment_id is not None:
            return int(assignment_id)

        for candidate in candidate_slugs:
            if not candidate:
                continue
            ratio = _similarity(assignment_slug, candidate)
            if ratio >= 0.9 and assignment_id is not None:
                return int(assignment_id)

    raise ValueError(
        "Could not resolve assignment ID from URL. Confirm token access and assignment URL."
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Automatically review GitHub Classroom assignments and "
            "generate a grade report."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--assignment-id",
        type=str,
        required=True,
        help="GitHub Classroom assignment ID or assignment URL to process.",
    )
    parser.add_argument(
        "--output",
        default="reports/grade_report.csv",
        help="Path for the output CSV grade report.",
    )
    parser.add_argument(
        "--extensions",
        nargs="*",
        metavar="EXT",
        help=(
            "Source file extensions to include in the review "
            "(e.g. --extensions .py .js). "
            "Defaults to a broad set of common code extensions."
        ),
    )
    parser.add_argument(
        "--model",
        default=os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b"),
        help="Ollama model to use for code reviews.",
    )
    parser.add_argument(
        "--instruction",
        default="",
        help="Instrução textual da atividade para guiar a correção.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run reviews but do NOT create GitHub issues.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    # Keep explicit load for backward compatibility in tests and local shells.
    load_dotenv()
    config = AppConfig.from_env(load_dotenv_file=False)
    args = _parse_args(argv)

    github_token = config.github_token
    ollama_host = config.ollama_host

    if not github_token:
        _log_error("Error: GITHUB_TOKEN is not set.")
        sys.exit(1)

    classroom_client = ClassroomClient(github_token)

    try:
        assignment_id = _resolve_assignment_id(args.assignment_id, classroom_client)
    except ValueError as exc:
        _log_error(f"Error: {exc}")
        sys.exit(1)

    github_client = GitHubClient(github_token)
    reviewer = CodeReviewer(model=args.model, base_url=ollama_host)
    reporter = GradeReporter()

    # ------------------------------------------------------------------ #
    # 1. Fetch assignment metadata
    # ------------------------------------------------------------------ #
    _log(f"Fetching assignment {assignment_id} …")
    assignment = classroom_client.get_assignment(assignment_id)
    assignment_title: str = assignment.get("title", f"Assignment {assignment_id}")
    _log(f"Assignment: {assignment_title}")

    # ------------------------------------------------------------------ #
    # 2. List all student submissions
    # ------------------------------------------------------------------ #
    _log("Fetching student submissions …")
    submissions = classroom_client.list_accepted_assignments(assignment_id)
    _log(f"Found {len(submissions)} submission(s).")

    if not submissions:
        _log("No submissions found. Exiting.")
        sys.exit(0)

    # ------------------------------------------------------------------ #
    # 3. Review each student repository
    # ------------------------------------------------------------------ #
    for idx, submission in enumerate(submissions, start=1):
        repo_full_name, student_login = _submission_identity(submission)

        _log(f"\n[{idx}/{len(submissions)}] {student_login} — {repo_full_name}")

        if not repo_full_name:
            _log("  Skipping: no repository found for this submission.")
            reporter.add_record(student_login, "", 0, "No repository found.", "")
            continue

        try:
            # Fetch source files
            files = github_client.get_repo_files(
                repo_full_name, extensions=args.extensions
            )
            if not files:
                _log("  No source files found — skipping review.")
                reporter.add_record(
                    student_login, repo_full_name, 0, "No source files found.", ""
                )
                continue

            _log(f"  Reviewing {len(files)} file(s) …")

            # AI review
            review = reviewer.review(
                repo_full_name,
                files,
                assignment_title,
                assignment_instruction=args.instruction,
            )
            grade = float(review.get("grade", 0))
            grade_comment: str = review.get("grade_comment", "")
            issue_url = ""

            # Create GitHub issue (unless --dry-run)
            if args.dry_run:
                _log("  [dry-run] Skipping issue creation.")
            else:
                issue_url = github_client.create_issue(
                    repo_full_name,
                    review.get("issue_title", "Code Review Feedback"),
                    review.get("issue_body", ""),
                )
                _log(f"  Issue created: {issue_url}")

            _log(
                f"  {student_login} - Nota: {grade:.1f}/10 — {grade_comment}"
            )
            reporter.add_record(
                student_login, repo_full_name, grade, grade_comment, issue_url
            )

        except Exception as exc:
            _log_error(f"  Error: {exc}")
            reporter.add_record(
                student_login, repo_full_name, 0, f"Error during review: {exc}", ""
            )

    # ------------------------------------------------------------------ #
    # 4. Export grade report
    # ------------------------------------------------------------------ #
    output_path = reporter.export_csv(args.output)
    _log(f"\nGrade report saved to: {output_path}")

    stats = reporter.summary()
    _log("\n=== Summary ===")
    _log(f"Students reviewed : {stats['count']}")
    _log(f"Average grade     : {stats['average']:.1f}/10")
    _log(f"Min / Max grade   : {stats['min']:.1f} / {stats['max']:.1f}")


if __name__ == "__main__":
    main()
