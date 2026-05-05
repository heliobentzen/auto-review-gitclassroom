"""CLI entry point for auto-review-gitclassroom.

Usage
-----
    python -m src.main --assignment-id <ID> [options]

Required environment variables (or .env file):
    GITHUB_TOKEN   — GitHub personal access token (repo + classroom scopes)
    OPENAI_API_KEY — OpenAI API key

Optional environment variables:
    OPENAI_MODEL   — OpenAI model name (default: gpt-4o-mini)
"""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

from .classroom_client import ClassroomClient
from .github_client import GitHubClient
from .reporter import GradeReporter
from .reviewer import CodeReviewer


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
        type=int,
        required=True,
        help="GitHub Classroom assignment ID to process.",
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
        default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        help="OpenAI model to use for code reviews.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run reviews but do NOT create GitHub issues.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    load_dotenv()
    args = _parse_args(argv)

    github_token = os.getenv("GITHUB_TOKEN")
    openai_api_key = os.getenv("OPENAI_API_KEY")

    if not github_token:
        print("Error: GITHUB_TOKEN is not set.", file=sys.stderr)
        sys.exit(1)
    if not openai_api_key:
        print("Error: OPENAI_API_KEY is not set.", file=sys.stderr)
        sys.exit(1)

    classroom_client = ClassroomClient(github_token)
    github_client = GitHubClient(github_token)
    reviewer = CodeReviewer(openai_api_key, model=args.model)
    reporter = GradeReporter()

    # ------------------------------------------------------------------ #
    # 1. Fetch assignment metadata
    # ------------------------------------------------------------------ #
    print(f"Fetching assignment {args.assignment_id} …")
    assignment = classroom_client.get_assignment(args.assignment_id)
    assignment_title: str = assignment.get("title", f"Assignment {args.assignment_id}")
    print(f"Assignment: {assignment_title}")

    # ------------------------------------------------------------------ #
    # 2. List all student submissions
    # ------------------------------------------------------------------ #
    print("Fetching student submissions …")
    submissions = classroom_client.list_accepted_assignments(args.assignment_id)
    print(f"Found {len(submissions)} submission(s).")

    if not submissions:
        print("No submissions found. Exiting.")
        sys.exit(0)

    # ------------------------------------------------------------------ #
    # 3. Review each student repository
    # ------------------------------------------------------------------ #
    for idx, submission in enumerate(submissions, start=1):
        repo_info = submission.get("repository", {})
        repo_full_name: str = repo_info.get("full_name", "")
        students: list[dict] = submission.get("students", [])
        student_login: str = (
            students[0]["login"] if students else repo_full_name.split("/")[-1]
        )

        print(f"\n[{idx}/{len(submissions)}] {student_login} — {repo_full_name}")

        if not repo_full_name:
            print("  Skipping: no repository found for this submission.")
            reporter.add_record(student_login, "", 0, "No repository found.", "")
            continue

        try:
            # Fetch source files
            files = github_client.get_repo_files(
                repo_full_name, extensions=args.extensions
            )
            if not files:
                print("  No source files found — skipping review.")
                reporter.add_record(
                    student_login, repo_full_name, 0, "No source files found.", ""
                )
                continue

            print(f"  Reviewing {len(files)} file(s) …")

            # AI review
            review = reviewer.review(repo_full_name, files, assignment_title)
            grade = float(review.get("grade", 0))
            grade_comment: str = review.get("grade_comment", "")
            issue_url = ""

            # Create GitHub issue (unless --dry-run)
            if args.dry_run:
                print("  [dry-run] Skipping issue creation.")
            else:
                issue_url = github_client.create_issue(
                    repo_full_name,
                    review.get("issue_title", "Code Review Feedback"),
                    review.get("issue_body", ""),
                )
                print(f"  Issue created: {issue_url}")

            print(f"  Grade: {grade:.1f}/10 — {grade_comment}")
            reporter.add_record(
                student_login, repo_full_name, grade, grade_comment, issue_url
            )

        except Exception as exc:
            print(f"  Error: {exc}", file=sys.stderr)
            reporter.add_record(
                student_login, repo_full_name, 0, f"Error during review: {exc}", ""
            )

    # ------------------------------------------------------------------ #
    # 4. Export grade report
    # ------------------------------------------------------------------ #
    output_path = reporter.export_csv(args.output)
    print(f"\nGrade report saved to: {output_path}")

    stats = reporter.summary()
    print("\n=== Summary ===")
    print(f"Students reviewed : {stats['count']}")
    print(f"Average grade     : {stats['average']:.1f}/10")
    print(f"Min / Max grade   : {stats['min']:.1f} / {stats['max']:.1f}")


if __name__ == "__main__":
    main()
