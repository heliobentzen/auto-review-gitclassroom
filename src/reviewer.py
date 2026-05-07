"""AI-powered code reviewer using a local Ollama model."""

from __future__ import annotations

import json
import os
import re
from typing import Any

import requests


_REVIEW_SYSTEM_PROMPT = """\
Você é professor de TI do IFPE (técnico integrado e superior em ADS) revisando código de alunos.

DIRETRIZES DE AVALIAÇÃO:
1. Idioma: Escreva tudo em Português do Brasil.
2. Foco Estrito: Avalie APENAS o contido nas "Instruções do professor". Ignore o que estiver fora do escopo.
3. Rubrica Obrigatória (Nota 0 a 10):
   - Estrutura e Sintaxe (30% - 3,0 pts): Avalie uso correto da tecnologia, compilação, organização e boas práticas básicas.
   - Cumprimento dos Requisitos (70% - 7,0 pts): Desconte proporcionalmente para cada exigência ausente ou implementada com estrutura incorreta (ex: usar contêiner vertical para layout lado a lado).
4. Recursos Extras: Se o aluno implementar itens não solicitados (ex: navegação onde pedia-se apenas tela estática), elogie no feedback, mas NUNCA compense pontos perdidos no básico nem exceda a nota máxima (10).
5. Omissões Permitidas: NÃO penalize ausência de arquitetura avançada, clean code, testes ou MVVM/MVI, salvo se explicitamente exigido.
6. Feedback: Seja didático e encorajador. Relacione cada erro diretamente à instrução. Se a instrução do professor for ambígua/incompleta, seja conservador no desconto da nota.

SAÍDA EXIGIDA:
Retorne EXCLUSIVAMENTE um JSON válido, sem uso de blocos Markdown (```json), contendo as chaves exatas:
{
   "issue_title": "<título curto>",
   "issue_body": "<Markdown com as seções exatas: ## Resumo, ## Cálculo da Nota (detalhando X/3.0, Y/7.0 e Z/10), ## Problemas Encontrados, ## Melhorias Sugeridas>",
   "grade": <número float de 0.0 a 10.0>,
   "grade_comment": "<comentário curto e didático justificando a nota com base na rubrica>"
}
"""

class CodeReviewer:
    """Uses Ollama to review source code and produce structured feedback."""

    def __init__(
        self,
        model: str = "qwen2.5-coder:7b",
        base_url: str = "http://localhost:11434",
        timeout: int = 300,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def review(
        self,
        repo_name: str,
        files: dict[str, str],
        assignment_title: str = "",
        assignment_instruction: str = "",
        analysis_level: str = "ensino_medio",
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
        user_message = self._build_user_message(
            repo_name=repo_name,
            files=files,
            assignment_title=assignment_title,
            assignment_instruction=assignment_instruction,
            analysis_level=analysis_level,
        )
        content = self._request_review_content(user_message)
        if not content:
            raise ValueError("Ollama returned an empty response.")
        return self._parse_json_response(content)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_user_message(
        self,
        *,
        repo_name: str,
        files: dict[str, str],
        assignment_title: str,
        assignment_instruction: str,
        analysis_level: str,
    ) -> str:
        code_block = self._format_files(files)
        expectation_level = self._normalize_expectation_level(analysis_level)
        return (
            "Atue como um professor avaliando o código de um aluno do curso técnico em informática integrado ao ensino médio.\n\n"
            f"Tarefa: {assignment_title or '(sem título informado)'}\n"
            f"Instruções do professor: {assignment_instruction or '(não informadas)'}\n\n"
            "Critérios de avaliação obrigatórios:\n"
            "- Estrutura e Sintaxe: 30% da nota (0 a 3,0 pontos).\n"
            "- Cumprimento dos Requisitos: 70% da nota (0 a 7,0 pontos).\n"
            "- Recursos extras não geram pontos adicionais e não compensam requisitos faltantes.\n\n"
            f"Nível de exigência: {expectation_level}\n"
            f"Repositório: {repo_name}\n\n"
            f"Código do aluno:\n\n{code_block}"
        )

    @staticmethod
    def _normalize_expectation_level(analysis_level: str) -> str:
        normalized = str(analysis_level or "").strip().lower()
        if normalized == "ensino_superior":
            return "nível de ensino superior"
        return "nível de ensino médio"

    def _request_review_content(self, user_message: str) -> str:
        if self._is_gemini_model():
            return self._request_gemini_review_content(user_message)

        response = requests.post(
            f"{self.base_url}/api/chat",
            json=self._build_payload(user_message),
            timeout=self.timeout,
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return str(data.get("message", {}).get("content", ""))

    def _request_gemini_review_content(self, user_message: str) -> str:
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY environment variable must be set when using Gemini models."
            )
        model_name = self._gemini_model_name()

        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent",
            json=self._build_gemini_payload(user_message),
            headers={"x-goog-api-key": api_key},
            timeout=self.timeout,
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        candidates = data.get("candidates", [])
        if not candidates:
            return ""
        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            return ""
        return str(parts[0].get("text", ""))

    def _is_gemini_model(self) -> bool:
        model_name = self._gemini_model_name().lower()
        return model_name.startswith("gemini")

    def _gemini_model_name(self) -> str:
        return self.model.strip().split("/", 1)[-1]

    def _build_payload(self, user_message: str) -> dict[str, Any]:
        return {
            "model": self.model,
            "format": "json",
            "stream": False,
            "messages": [
                {"role": "system", "content": _REVIEW_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            "options": {"temperature": 0.2},
        }

    def _build_gemini_payload(self, user_message: str) -> dict[str, Any]:
        return {
            "system_instruction": {"parts": [{"text": _REVIEW_SYSTEM_PROMPT}]},
            "contents": [{"parts": [{"text": user_message}]}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }

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

    @staticmethod
    def _parse_json_response(content: str) -> dict:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # Some local models wrap JSON with extra text; recover the first object.
            start = content.find("{")
            end = content.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise

            candidate = content[start : end + 1]
            candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
            return json.loads(candidate)
