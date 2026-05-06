from __future__ import annotations

from src import webapp


def _new_job() -> str:
    job_id = "job-test-id"
    with webapp.JOBS_LOCK:
        webapp.JOBS[job_id] = webapp.JobState(
            id=job_id,
            assignment="10",
            instruction="",
            analysis_level="intermediario",
            model="qwen2.5-coder:1.5b",
            extensions=[".kt"],
            status="ready_for_review",
            drafts=[
                webapp.StudentDraft(
                    student="alice",
                    repository="org/alice-repo",
                    grade=8.0,
                    grade_comment="Bom",
                    issue_title="Feedback",
                    issue_body="Corpo",
                ),
                webapp.StudentDraft(
                    student="bob",
                    repository="org/bob-repo",
                    grade=7.0,
                    grade_comment="Ok",
                    issue_title="Feedback",
                    issue_body="Corpo",
                ),
            ],
        )
    return job_id


def test_api_save_creates_one_issue_per_known_student(monkeypatch, mocker):
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    job_id = _new_job()

    fake_github = mocker.MagicMock()
    fake_github.create_issue.side_effect = [
        "https://github.com/org/alice-repo/issues/1",
        "https://github.com/org/bob-repo/issues/1",
    ]
    mocker.patch("src.webapp.GitHubClient", return_value=fake_github)

    client = webapp.app.test_client()
    res = client.post(
        f"/api/save/{job_id}",
        json={
            "drafts": [
                {
                    "repository": "org/alice-repo",
                    "student": "alice",
                    "issue_title": "A",
                    "issue_body": "B",
                },
                {
                    "repository": "org/bob-repo",
                    "student": "bob",
                    "issue_title": "C",
                    "issue_body": "D",
                },
            ]
        },
    )

    assert res.status_code == 200
    data = res.get_json()
    assert data["created"] == 2
    assert data["skipped"] == 0
    assert data["failed"] == 0
    assert len(data["created_details"]) == 2
    assert data["failed_details"] == []
    assert fake_github.create_issue.call_count == 2

    with webapp.JOBS_LOCK:
        drafts = webapp.JOBS[job_id].drafts
        assert drafts[0].status == "published"
        assert drafts[0].issue_url.endswith("/issues/1")
        assert drafts[1].status == "published"
        assert drafts[1].issue_url.endswith("/issues/1")



def test_api_save_ignores_payload_entries_outside_job(monkeypatch, mocker):
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    job_id = _new_job()

    fake_github = mocker.MagicMock()
    fake_github.create_issue.return_value = "https://github.com/org/alice-repo/issues/1"
    mocker.patch("src.webapp.GitHubClient", return_value=fake_github)

    client = webapp.app.test_client()
    res = client.post(
        f"/api/save/{job_id}",
        json={
            "drafts": [
                {
                    "repository": "org/other-repo",
                    "student": "mallory",
                    "issue_title": "X",
                    "issue_body": "Y",
                }
            ]
        },
    )

    assert res.status_code == 200
    data = res.get_json()
    assert data["created"] == 0
    assert data["failed"] == 0
    assert data["skipped"] == 3
    reasons = {d["reason"] for d in data["skipped_details"]}
    assert "fora_do_job" in reasons
    assert "sem_edicao_no_payload" in reasons
    fake_github.create_issue.assert_not_called()



def test_api_save_is_idempotent_for_published_draft(monkeypatch, mocker):
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    job_id = _new_job()

    fake_github = mocker.MagicMock()
    fake_github.create_issue.return_value = "https://github.com/org/alice-repo/issues/1"
    mocker.patch("src.webapp.GitHubClient", return_value=fake_github)

    client = webapp.app.test_client()
    payload = {
        "drafts": [
            {
                "repository": "org/alice-repo",
                "student": "alice",
                "issue_title": "A",
                "issue_body": "B",
            }
        ]
    }

    first = client.post(f"/api/save/{job_id}", json=payload)
    second = client.post(f"/api/save/{job_id}", json=payload)

    assert first.status_code == 200
    first_data = first.get_json()
    assert first_data["created"] == 1
    assert first_data["failed"] == 0
    assert second.status_code == 200
    second_data = second.get_json()
    assert second_data["created"] == 0
    assert second_data["failed"] == 0
    assert second_data["skipped"] >= 1
    assert any(d["reason"] == "ja_publicada" for d in second_data["skipped_details"])
    assert fake_github.create_issue.call_count == 1


def test_api_save_reports_failed_issue_creation(monkeypatch, mocker):
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    job_id = _new_job()

    fake_github = mocker.MagicMock()
    fake_github.create_issue.side_effect = RuntimeError("sem permissao")
    mocker.patch("src.webapp.GitHubClient", return_value=fake_github)

    client = webapp.app.test_client()
    res = client.post(
        f"/api/save/{job_id}",
        json={
            "drafts": [
                {
                    "repository": "org/alice-repo",
                    "student": "alice",
                    "issue_title": "A",
                    "issue_body": "B",
                }
            ]
        },
    )

    assert res.status_code == 200
    data = res.get_json()
    assert data["created"] == 0
    assert data["failed"] == 1
    assert data["failed_details"][0]["student"] == "alice"
    assert "sem permissao" in data["failed_details"][0]["error"]
