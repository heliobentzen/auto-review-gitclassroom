"""Grade report generator — collects per-student results and exports to CSV."""

from __future__ import annotations

import csv
import os


_FIELDNAMES = ["student", "repository", "grade", "grade_comment", "issue_url"]


class GradeReporter:
    """Accumulates per-student review results and exports them to a CSV file."""

    def __init__(self) -> None:
        self._records: list[dict] = []

    # ------------------------------------------------------------------
    # Record collection
    # ------------------------------------------------------------------

    def add_record(
        self,
        student_login: str,
        repo_full_name: str,
        grade: float,
        grade_comment: str,
        issue_url: str = "",
    ) -> None:
        """Add one student's result to the report.

        Parameters
        ----------
        student_login:
            GitHub username of the student.
        repo_full_name:
            Repository in ``owner/repo`` format.
        grade:
            Numeric grade on a 0–10 scale.
        grade_comment:
            Short explanation of the grade.
        issue_url:
            URL of the review issue created on the student's repo (may be empty).
        """
        self._records.append(
            {
                "student": student_login,
                "repository": repo_full_name,
                "grade": grade,
                "grade_comment": grade_comment,
                "issue_url": issue_url,
            }
        )

    @property
    def records(self) -> list[dict]:
        """Return a copy of all accumulated records."""
        return list(self._records)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_csv(self, output_path: str) -> str:
        """Write all records to a CSV file and return the resolved path.

        Parent directories are created automatically if they do not exist.
        """
        parent = os.path.dirname(output_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        with open(output_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=_FIELDNAMES)
            writer.writeheader()
            writer.writerows(self._records)

        return output_path

    # ------------------------------------------------------------------
    # Summary statistics
    # ------------------------------------------------------------------

    def summary(self) -> dict:
        """Return basic statistics over all recorded grades.

        Returns
        -------
        dict
            Keys: ``count``, ``average``, ``min``, ``max``.
        """
        grades = [r["grade"] for r in self._records]
        if not grades:
            return {"count": 0, "average": 0.0, "min": 0.0, "max": 0.0}
        return {
            "count": len(grades),
            "average": sum(grades) / len(grades),
            "min": min(grades),
            "max": max(grades),
        }
