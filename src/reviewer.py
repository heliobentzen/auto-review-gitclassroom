"""AI-powered code reviewer using a local Ollama model."""

from __future__ import annotations

import json
import re
from typing import Any

import requests


_REVIEW_SYSTEM_PROMPT = """\
Você é um professor de desenvolvimento de software revisando código de estudantes.

Regras da análise:
1. Escreva tudo em português do Brasil.
2. Foque na execução da atividade pedida pelo professor.
3. Avalie SOMENTE critérios explicitamente pedidos nas "Instruções do professor".
4. Não cobre requisitos extras que não foram solicitados.
5. NÃO penalize por ausência de arquitetura avançada, padrões de projeto, otimizações,
     testes automatizados, segurança avançada, clean architecture, MVVM/MVI ou refatorações grandes,
     a menos que isso esteja explicitamente nas instruções.
6. Quando citar problemas, relacione cada um diretamente a um pedido da atividade.
7. Se algum aspecto estiver fora do escopo, ignore esse aspecto.
8. Não proponha soluções robustas/complexas (arquiteturas avançadas, padrões excessivos,
     refatorações grandes). Priorize correções diretas e melhorias objetivas no escopo.
9. Dê nota de 0 a 10 considerando o nível técnico do estudante e apenas o escopo pedido.

Formato obrigatório do conteúdo:
- issue_title: título curto em português, sem exigir itens fora do escopo.
- issue_body: Markdown com seções exatas:
    ## Resumo
    ## Problemas Encontrados
    ## Melhorias Sugeridas
- Em "Problemas Encontrados" e "Melhorias Sugeridas", descreva apenas itens ligados à instrução.
- grade_comment: comentário curto explicando a nota com base apenas no que foi solicitado.

Responda SOMENTE com um JSON válido, com estas chaves exatas:
{
    "issue_title": "<título curto em português>",
    "issue_body": "<Markdown em português com seções: ## Resumo, ## Problemas Encontrados, ## Melhorias Sugeridas>",
    "grade": <número de 0 a 10>,
    "grade_comment": "<comentário curto em português explicando a nota>"
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
        analysis_level: str = "intermediario",
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
        return (
            f"Atividade: {assignment_title}\n"
            f"Instruções do professor: {assignment_instruction or '(não informadas)'}\n"
            f"Nível desejado da análise: {analysis_level}\n"
            f"Repositório: {repo_name}\n\n"
            f"Arquivos para revisar:\n\n{code_block}"
        )

    def _request_review_content(self, user_message: str) -> str:
        response = requests.post(
            f"{self.base_url}/api/chat",
            json=self._build_payload(user_message),
            timeout=self.timeout,
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return str(data.get("message", {}).get("content", ""))

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
