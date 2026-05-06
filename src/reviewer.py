"""AI-powered code reviewer with Ollama and Gemini providers."""

from __future__ import annotations

import json
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
6. Sem Overengineering (qualquer linguagem): NÃO exija padrões arquiteturais específicos (ex: ViewModel/MVVM, Clean Architecture, DI, ORMs avançados, camadas extras, testes automatizados) quando a atividade não pedir isso de forma explícita.
7. Obrigatório vs Recomendado: Diferencie claramente requisito obrigatório de boa prática recomendada. Boa prática não cumprida NÃO deve virar desconto de nota, a menos que esteja na instrução do professor.
8. Proporcionalidade: Se o aluno acertou a maior parte da atividade e existe apenas uma ou poucas falhas pontuais, aplique desconto proporcional. Não zere ou derrube a nota para faixas muito baixas quando a entrega estiver majoritariamente correta.
9. Prioridade dos Achados: Destaque primeiro falhas funcionais e de requisitos. Itens de clean code, código não utilizado ou organização só devem aparecer como observações secundárias quando não forem o principal problema da atividade.
10. Concisão: Liste no máximo 3 problemas principais. Se houver apenas 1 problema relevante, concentre a issue nele em vez de inflar a análise com observações menores.
11. Formato Enxuto da Entrega: Resuma a avaliação em problemas objetivos da entrega da feature. Evite checklist extenso de boas práticas. A seção de melhorias deve ser curta e opcional.
12. Melhorias no Máximo: Em "## Melhorias Sugeridas", inclua no máximo 2 itens, apenas quando forem diretamente necessários para corrigir os problemas listados; se não houver, escreva "Sem melhorias adicionais".
13. Feedback: Seja didático e encorajador. Relacione cada erro diretamente à instrução. Se a instrução do professor for ambígua/incompleta, seja conservador no desconto da nota.

SAÍDA EXIGIDA:
Retorne EXCLUSIVAMENTE um JSON válido, sem uso de blocos Markdown (```json), contendo as chaves exatas:
{
   "issue_title": "<título curto>",
   "issue_body": "<Markdown com as seções exatas: ## Resumo, ## Cálculo da Nota (detalhando X/3.0, Y/7.0 e Z/10), ## Problemas Encontrados, ## Melhorias Sugeridas>",
   "grade": <número float de 0.0 a 10.0>,
   "grade_comment": "<comentário curto e didático justificando a nota com base na rubrica>"
}

Estilo esperado da resposta:
- Pareça uma issue real de professor, objetiva e útil para o aluno.
- No "## Problemas Encontrados", priorize 1 a 3 pontos principais, em ordem de impacto.
- No "## Melhorias Sugeridas", proponha correções diretas e práticas somente para os problemas listados (máximo 2 itens).
- Se houver código não utilizado ou ajuste menor, cite isso somente depois do problema funcional principal.
"""

class CodeReviewer:
    """Uses Ollama or Gemini to review source code and produce feedback."""

    def __init__(
        self,
        model: str = "qwen2.5-coder:7b",
        base_url: str = "http://localhost:11434",
        provider: str = "ollama",
        gemini_api_key: str = "",
        timeout: int = 300,
    ) -> None:
        self.provider = str(provider or "ollama").strip().lower()
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.gemini_api_key = gemini_api_key
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
            "Regras de aderência ao enunciado:\n"
            "- Esta regra vale para qualquer linguagem (Kotlin, Java, Python, JavaScript, C, etc.).\n"
            "- Não exija arquitetura/padrões avançados (ViewModel, MVVM/MVI, DI, Clean Architecture, ORMs avançados, testes unitários) salvo quando a instrução pedir explicitamente.\n"
            "- Não converta boa prática recomendada em requisito obrigatório para desconto de nota.\n"
            "- Se a solução atender ao enunciado com abordagem simples e correta, considere como suficiente para boa nota.\n\n"
            "Ao encontrar poucas falhas pontuais em uma entrega majoritariamente correta, aplique desconto proporcional e mantenha a nota coerente com o conjunto da solução.\n\n"
            "Na issue final, priorize os problemas funcionais e liste no máximo 3 achados principais. Se existir apenas um erro central, concentre a análise nele. Observações de clean code ou código não utilizado devem aparecer apenas como secundárias.\n"
            "Na seção de melhorias, inclua no máximo 2 ações corretivas, somente se forem necessárias para corrigir os problemas; caso contrário, escreva 'Sem melhorias adicionais'.\n\n"
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
        if self.provider == "gemini":
            return self._request_gemini_content(user_message)
        if self.provider != "ollama":
            raise ValueError(f"Unsupported provider: {self.provider}")

        return self._request_ollama_content(user_message)

    def _request_ollama_content(self, user_message: str) -> str:
        chat_endpoint = f"{self.base_url}/api/chat"
        generate_endpoint = f"{self.base_url}/api/generate"

        response = requests.post(
            chat_endpoint,
            json=self._build_ollama_payload(user_message),
            timeout=self.timeout,
        )

        try:
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            return str(data.get("message", {}).get("content", ""))
        except requests.HTTPError as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code != 404:
                raise

        # Compatibilidade com servidores que expõem apenas /api/generate.
        fallback_response = requests.post(
            generate_endpoint,
            json=self._build_ollama_generate_payload(user_message),
            timeout=self.timeout,
        )
        try:
            fallback_response.raise_for_status()
        except requests.HTTPError as exc:
            raise requests.HTTPError(
                "Falha ao acessar Ollama. O endpoint /api/chat retornou 404 e o fallback "
                f"/api/generate também falhou em {self.base_url}."
            ) from exc

        fallback_data: dict[str, Any] = fallback_response.json()
        return str(fallback_data.get("response", ""))

    def _request_gemini_content(self, user_message: str) -> str:
        if not self.gemini_api_key:
            raise ValueError("GEMINI_API_KEY não configurado para o provedor Gemini.")

        endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
            f"?key={self.gemini_api_key}"
        )

        response = requests.post(
            endpoint,
            json=self._build_gemini_payload(user_message),
            timeout=self.timeout,
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()

        candidates = data.get("candidates") or []
        if not candidates:
            return ""

        parts = candidates[0].get("content", {}).get("parts") or []
        texts = [str(part.get("text", "")) for part in parts if part.get("text")]
        return "\n".join(texts).strip()

    def _build_ollama_payload(self, user_message: str) -> dict[str, Any]:
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

    def _build_ollama_generate_payload(self, user_message: str) -> dict[str, Any]:
        return {
            "model": self.model,
            "format": "json",
            "stream": False,
            "prompt": f"{_REVIEW_SYSTEM_PROMPT}\n\n{user_message}",
            "options": {"temperature": 0.2},
        }

    def _build_gemini_payload(self, user_message: str) -> dict[str, Any]:
        return {
            "system_instruction": {
                "parts": [{"text": _REVIEW_SYSTEM_PROMPT}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_message}],
                }
            ],
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
