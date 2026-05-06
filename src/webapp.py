"""Web interface for classroom review workflow.

Flow:
1. Professor starts a preview run with assignment URL + instructions.
2. App shows terminal-like progress and generated draft reviews per student.
3. Professor edits all draft comments.
4. App publishes GitHub issues with the edited content.
"""

from __future__ import annotations

import os
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from flask import Flask, jsonify, request

from .classroom_client import ClassroomClient
from .config import AppConfig
from .github_client import DEFAULT_CODE_EXTENSIONS, GitHubClient
from .main import _resolve_assignment_id
from .reviewer import CodeReviewer

load_dotenv()

app = Flask(__name__)
_STATIC_INDEX_PATH = Path(__file__).resolve().parent / "static" / "index.html"


@dataclass
class StudentDraft:
    student: str
    repository: str
    grade: float
    grade_comment: str
    issue_title: str
    issue_body: str
    issue_url: str = ""
    status: str = "draft"


@dataclass
class JobState:
    id: str
    assignment: str
    instruction: str
    analysis_level: str
    provider: str
    model: str
    extensions: list[str]
    status: str = "running"
    logs: list[str] = field(default_factory=list)
    drafts: list[StudentDraft] = field(default_factory=list)
    error: str = ""
    cancel_requested: bool = False


JOBS: dict[str, JobState] = {}
JOBS_LOCK = threading.Lock()
DraftKey = tuple[str, str]


def _append_log(job_id: str, message: str) -> None:
    with JOBS_LOCK:
        job = JOBS[job_id]
        job.logs.append(message)


def _set_job_error(job_id: str, message: str) -> None:
    with JOBS_LOCK:
        job = JOBS[job_id]
        job.status = "failed"
        job.error = message
        job.logs.append(f"ERRO: {message}")


def _set_job_done(job_id: str) -> None:
    with JOBS_LOCK:
        if JOBS[job_id].cancel_requested:
            JOBS[job_id].status = "canceled"
            JOBS[job_id].logs.append("Execução cancelada pelo usuário.")
        else:
            JOBS[job_id].status = "ready_for_review"


def _is_cancel_requested(job_id: str) -> bool:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        return bool(job and job.cancel_requested)


def _normalize_edited_drafts(edited_drafts: list[dict[str, Any]]) -> dict[DraftKey, dict[str, str]]:
    normalized: dict[DraftKey, dict[str, str]] = {}
    for edited in edited_drafts:
        repo = str(edited.get("repository", "")).strip()
        student = str(edited.get("student", "")).strip()
        if not repo or not student:
            continue
        normalized[(repo, student)] = {
            "issue_title": str(edited.get("issue_title", "Feedback da atividade")),
            "issue_body": str(edited.get("issue_body", "")),
        }
    return normalized


def _snapshot_job_drafts(job_id: str) -> list[StudentDraft]:
    with JOBS_LOCK:
        return [d for d in JOBS[job_id].drafts]


def _mark_published_draft(
    job_id: str,
    *,
    repo: str,
    student: str,
    title: str,
    body: str,
    issue_url: str,
) -> None:
    with JOBS_LOCK:
        for draft in JOBS[job_id].drafts:
            if draft.repository == repo and draft.student == student:
                draft.issue_title = title
                draft.issue_body = body
                draft.issue_url = issue_url
                draft.status = "published"
                break


def _normalize_base_path(path: str) -> str:
    cleaned = str(path or "").strip()
    if not cleaned or cleaned == "/":
        return ""
    if not cleaned.startswith("/"):
        cleaned = f"/{cleaned}"
    return cleaned.rstrip("/")

def _get_job(job_id: str) -> JobState | None:
    with JOBS_LOCK:
        return JOBS.get(job_id)


def _create_job(payload: dict[str, Any]) -> str:
    assignment = str(payload.get("assignment", "")).strip()
    instruction = str(payload.get("instruction", "")).strip()
    analysis_level = str(payload.get("analysis_level", "ensino_medio")).strip()
    raw_provider = str(payload.get("provider", "")).strip().lower()
    raw_model = str(payload.get("model", "")).strip()

    if raw_provider in {"ollama", "gemini"}:
        provider = raw_provider
    elif raw_model.lower().startswith("gemini"):
        provider = "gemini"
    else:
        provider = "ollama"

    default_model = "qwen2.5-coder:1.5b" if provider == "ollama" else "gemini-1.5-flash"
    model = raw_model or default_model

    # Se o modelo for Gemini, force o roteamento para Gemini para evitar erro em /api/chat.
    if model.lower().startswith("gemini"):
        provider = "gemini"

    extensions = payload.get("extensions") or list(DEFAULT_CODE_EXTENSIONS)

    job_id = str(uuid.uuid4())
    with JOBS_LOCK:
        JOBS[job_id] = JobState(
            id=job_id,
            assignment=assignment,
            instruction=instruction,
            analysis_level=analysis_level,
            provider=provider,
            model=model,
            extensions=extensions,
        )
    return job_id


def _serialize_job(job: JobState) -> dict[str, Any]:
    return {
        "id": job.id,
        "status": job.status,
        "error": job.error,
        "logs": list(job.logs),
        "drafts": [d.__dict__ for d in job.drafts],
    }


def _publish_issues_for_job(
    job_id: str,
    edited_drafts: list[dict[str, Any]],
    github_client: GitHubClient,
) -> dict[str, Any]:
    edited_by_key = _normalize_edited_drafts(edited_drafts)

    created_details: list[dict[str, str]] = []
    skipped_details: list[dict[str, str]] = []
    failed_details: list[dict[str, str]] = []

    draft_snapshot = _snapshot_job_drafts(job_id)
    valid_keys = {(d.repository, d.student) for d in draft_snapshot}

    for repo, student in edited_by_key:
        if (repo, student) not in valid_keys:
            skipped_details.append(
                {
                    "student": student,
                    "repository": repo,
                    "reason": "fora_do_job",
                }
            )

    for draft in draft_snapshot:
        repo = draft.repository
        student = draft.student
        key = (repo, student)

        edited = edited_by_key.get(key)
        if not edited:
            skipped_details.append(
                {
                    "student": student,
                    "repository": repo,
                    "reason": "sem_edicao_no_payload",
                }
            )
            continue

        if draft.status == "published":
            _append_log(job_id, f"Issue já publicada para {student}: {draft.issue_url}")
            skipped_details.append(
                {
                    "student": student,
                    "repository": repo,
                    "reason": "ja_publicada",
                }
            )
            continue

        title = edited["issue_title"]
        body = edited["issue_body"]

        try:
            url = github_client.create_issue(repo, title, body)
            created_details.append(
                {
                    "student": student,
                    "repository": repo,
                    "url": url,
                }
            )
            _append_log(job_id, f"Issue criada para {student}: {url}")
            _mark_published_draft(
                job_id,
                repo=repo,
                student=student,
                title=title,
                body=body,
                issue_url=url,
            )
        except Exception as exc:  # noqa: BLE001
            _append_log(job_id, f"Erro ao criar issue para {student}: {exc}")
            failed_details.append(
                {
                    "student": student,
                    "repository": repo,
                    "error": str(exc),
                }
            )

    return {
        "created": len(created_details),
        "skipped": len(skipped_details),
        "failed": len(failed_details),
        "created_details": created_details,
        "skipped_details": skipped_details,
        "failed_details": failed_details,
    }


def _run_preview(job_id: str) -> None:
    config = AppConfig.from_env(load_dotenv_file=False)
    token = config.github_token
    if not token:
        _set_job_error(job_id, "GITHUB_TOKEN não configurado.")
        return

    ollama_host = config.ollama_host
    gemini_api_key = config.gemini_api_key

    with JOBS_LOCK:
        job = JOBS[job_id]
        assignment = job.assignment
        instruction = job.instruction
        analysis_level = job.analysis_level
        provider = job.provider
        model = job.model
        extensions = job.extensions

    if provider == "gemini" and not gemini_api_key:
        _set_job_error(job_id, "GEMINI_API_KEY não configurado para usar Gemini.")
        return

    classroom_client = ClassroomClient(token)
    github_client = GitHubClient(token)
    reviewer = CodeReviewer(
        provider=provider,
        model=model,
        base_url=ollama_host,
        gemini_api_key=gemini_api_key,
    )

    try:
        assignment_id = _resolve_assignment_id(assignment, classroom_client)
        assignment_data = classroom_client.get_assignment(assignment_id)
        assignment_title = assignment_data.get("title", f"Atividade {assignment_id}")

        _append_log(job_id, f"Carregando atividade {assignment_id} …")
        _append_log(job_id, f"Atividade: {assignment_title}")
        _append_log(job_id, "Buscando submissões dos alunos …")

        submissions = classroom_client.list_accepted_assignments(assignment_id)
        _append_log(job_id, f"Encontradas {len(submissions)} submissão(ões).")

        for idx, submission in enumerate(submissions, start=1):
            if _is_cancel_requested(job_id):
                _set_job_done(job_id)
                return

            repo_info = submission.get("repository", {})
            repo_full_name = repo_info.get("full_name", "")
            students = submission.get("students", [])
            student_login = (
                students[0]["login"] if students else repo_full_name.split("/")[-1]
            )

            _append_log(
                job_id,
                f"[{idx}/{len(submissions)}] {student_login} — {repo_full_name}",
            )

            if not repo_full_name:
                _append_log(job_id, "  Pulando: repositório não encontrado para esta submissão.")
                continue

            try:
                files = github_client.get_repo_files(repo_full_name, extensions=extensions)
                if not files:
                    _append_log(job_id, "  Nenhum arquivo de código encontrado — pulando revisão.")
                    continue

                _append_log(job_id, f"  Revisando {len(files)} arquivo(s) …")
                review = reviewer.review(
                    repo_full_name,
                    files,
                    assignment_title,
                    assignment_instruction=instruction,
                    analysis_level=analysis_level,
                )
                grade = float(review.get("grade", 0))
                grade_comment = review.get("grade_comment", "")

                with JOBS_LOCK:
                    JOBS[job_id].drafts.append(
                        StudentDraft(
                            student=student_login,
                            repository=repo_full_name,
                            grade=grade,
                            grade_comment=grade_comment,
                            issue_title=review.get("issue_title", "Feedback da atividade"),
                            issue_body=review.get("issue_body", ""),
                        )
                    )

                _append_log(
                    job_id,
                    f"  {student_login} - Nota: {grade:.1f}/10 — {grade_comment}",
                )

            except Exception as exc:  # noqa: BLE001
                _append_log(job_id, f"  Erro: {exc}")

        _set_job_done(job_id)

    except Exception as exc:  # noqa: BLE001
        _set_job_error(job_id, str(exc))


@app.get("/")
def index() -> str:
    config = AppConfig.from_env(load_dotenv_file=False)
    base_path = _normalize_base_path(config.app_base_path)
    html = _STATIC_INDEX_PATH.read_text(encoding="utf-8")
    return html.replace("__APP_BASE_PATH__", base_path)


@app.post("/api/start")
def api_start() -> Any:
    payload = request.get_json(silent=True) or {}
    assignment = str(payload.get("assignment", "")).strip()

    if not assignment:
        return jsonify({"error": "Informe a URL/ID da assignment."}), 400

    job_id = _create_job(payload)

    thread = threading.Thread(target=_run_preview, args=(job_id,), daemon=True)
    thread.start()

    return jsonify({"job_id": job_id})


@app.post("/api/stop/<job_id>")
def api_stop(job_id: str) -> Any:
  with JOBS_LOCK:
    job = JOBS.get(job_id)
    if not job:
      return jsonify({"error": "Job não encontrado."}), 404

    if job.status not in {"running", "stopping"}:
      return jsonify({"error": "Este job não está em execução."}), 400

    job.cancel_requested = True
    job.status = "stopping"
    job.logs.append("Solicitação de parada recebida. Finalizando etapa atual...")

    return jsonify({"ok": True})


@app.get("/api/status/<job_id>")
def api_status(job_id: str) -> Any:
    job = _get_job(job_id)
    if not job:
        return jsonify({"error": "Job não encontrado."}), 404
    return jsonify(_serialize_job(job))


@app.post("/api/save/<job_id>")
def api_save(job_id: str) -> Any:
    config = AppConfig.from_env(load_dotenv_file=False)
    token = config.github_token
    if not token:
        return jsonify({"error": "GITHUB_TOKEN não configurado."}), 400

    if not _get_job(job_id):
        return jsonify({"error": "Job não encontrado."}), 404

    payload = request.get_json(silent=True) or {}
    edited_drafts = payload.get("drafts") or []
    github_client = GitHubClient(token)
    result = _publish_issues_for_job(job_id, edited_drafts, github_client)
    return jsonify(result)


def run() -> None:
    app.run(host="127.0.0.1", port=8000, debug=False)


if __name__ == "__main__":
    run()
