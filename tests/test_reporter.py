"""Tests for GradeReporter."""

from __future__ import annotations

import csv
import os

import pytest

from src.reporter import GradeReporter


@pytest.fixture
def reporter():
    return GradeReporter()


@pytest.fixture
def populated_reporter():
    r = GradeReporter()
    r.add_record("alice", "org/alice-repo", 8.5, "Great work.", "https://github.com/org/alice-repo/issues/1")
    r.add_record("bob", "org/bob-repo", 6.0, "Needs improvement.", "")
    r.add_record("carol", "org/carol-repo", 9.0, "Excellent.", "https://github.com/org/carol-repo/issues/1")
    return r


class TestAddRecord:
    def test_single_record(self, reporter):
        reporter.add_record("alice", "org/repo", 7.0, "Good job.")
        assert len(reporter.records) == 1

    def test_record_fields(self, reporter):
        reporter.add_record("alice", "org/repo", 7.5, "Well done.", "https://example.com")
        rec = reporter.records[0]
        assert rec["student"] == "alice"
        assert rec["repository"] == "org/repo"
        assert rec["grade"] == 7.5
        assert rec["grade_comment"] == "Well done."
        assert rec["issue_url"] == "https://example.com"

    def test_default_issue_url_empty(self, reporter):
        reporter.add_record("alice", "org/repo", 5.0, "Average.")
        assert reporter.records[0]["issue_url"] == ""

    def test_multiple_records(self, reporter):
        for i in range(5):
            reporter.add_record(f"student{i}", f"org/repo{i}", float(i), "comment")
        assert len(reporter.records) == 5

    def test_records_property_returns_copy(self, reporter):
        reporter.add_record("alice", "org/repo", 7.0, "Good.")
        copy = reporter.records
        copy.clear()
        assert len(reporter.records) == 1  # original unaffected


class TestExportCsv:
    def test_creates_file(self, reporter, tmp_path):
        reporter.add_record("alice", "org/repo", 8.0, "Good.")
        output = str(tmp_path / "report.csv")
        reporter.export_csv(output)
        assert os.path.exists(output)

    def test_csv_headers(self, reporter, tmp_path):
        output = str(tmp_path / "report.csv")
        reporter.export_csv(output)
        with open(output, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            assert set(reader.fieldnames) == {
                "student", "repository", "grade", "grade_comment", "issue_url"
            }

    def test_csv_content(self, populated_reporter, tmp_path):
        output = str(tmp_path / "grades.csv")
        populated_reporter.export_csv(output)
        with open(output, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        assert len(rows) == 3
        assert rows[0]["student"] == "alice"
        assert rows[1]["grade"] == "6.0"
        assert rows[2]["grade_comment"] == "Excellent."

    def test_creates_parent_directories(self, reporter, tmp_path):
        output = str(tmp_path / "nested" / "dir" / "report.csv")
        reporter.export_csv(output)
        assert os.path.exists(output)

    def test_returns_output_path(self, reporter, tmp_path):
        output = str(tmp_path / "report.csv")
        returned = reporter.export_csv(output)
        assert returned == output

    def test_empty_reporter_writes_header_only(self, reporter, tmp_path):
        output = str(tmp_path / "empty.csv")
        reporter.export_csv(output)
        with open(output, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        assert rows == []


class TestSummary:
    def test_empty_reporter(self, reporter):
        s = reporter.summary()
        assert s == {"count": 0, "average": 0.0, "min": 0.0, "max": 0.0}

    def test_single_record(self, reporter):
        reporter.add_record("alice", "org/repo", 7.0, "Good.")
        s = reporter.summary()
        assert s["count"] == 1
        assert s["average"] == 7.0
        assert s["min"] == 7.0
        assert s["max"] == 7.0

    def test_multiple_records(self, populated_reporter):
        s = populated_reporter.summary()
        assert s["count"] == 3
        assert s["min"] == 6.0
        assert s["max"] == 9.0
        assert abs(s["average"] - (8.5 + 6.0 + 9.0) / 3) < 1e-9
