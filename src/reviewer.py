"""AI-powered code reviewer with Ollama and Gemini providers."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)


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
        gemini_model: str = "gemini-2.5-flash",
        timeout: int = 300,
    ) -> None:
        self.provider = str(provider or "ollama").strip().lower()
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.gemini_api_key = gemini_api_key
        self.gemini_model = str(gemini_model or "gemini-2.5-flash").strip()
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
            raise ValueError(
                f"{self.provider.capitalize()} retornou resposta vazia. "
                "O modelo pode ter filtrado o conteúdo ou o prompt excedeu o limite."
            )
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
        model_hint = self._normalize_gemini_model_name(self.model).lower()
        if model_hint.startswith("gemini"):
            return self._request_gemini_content(user_message)

        if self.provider == "gemini":
            return self._request_gemini_content(user_message)
        if self.provider != "ollama":
            raise ValueError(f"Unsupported provider: {self.provider}")

        return self._request_ollama_content(user_message)

    def _request_ollama_content(self, user_message: str) -> str:
        chat_endpoint = f"{self.base_url}/api/chat"
        generate_endpoint = f"{self.base_url}/api/generate"

        chat_response: Any | None = None
        try:
            chat_response = requests.post(
                chat_endpoint,
                json=self._build_ollama_payload(user_message),
                timeout=self.timeout,
            )

            chat_response.raise_for_status()
            data: dict[str, Any] = chat_response.json()
            return str(data.get("message", {}).get("content", ""))
        except requests.HTTPError as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code is None and chat_response is not None:
                status_code = getattr(chat_response, "status_code", None)

            # Se não for 404, tenta Gemini (quando disponível) antes de propagar.
            if status_code != 404:
                if self.gemini_api_key:
                    return self._request_gemini_content(
                        user_message,
                        model_name=self._resolve_gemini_model_name(),
                    )
                raise

            # /api/chat não existe em algumas instalações antigas.
            try:
                fallback_response = requests.post(
                    generate_endpoint,
                    json=self._build_ollama_generate_payload(user_message),
                    timeout=self.timeout,
                )
                fallback_response.raise_for_status()
                fallback_data: dict[str, Any] = fallback_response.json()
                return str(fallback_data.get("response", ""))
            except requests.RequestException as fallback_exc:
                # Segurança operacional: se Ollama falhar e houver chave Gemini,
                # tenta Gemini automaticamente para evitar interrupção da turma.
                if self.gemini_api_key:
                    return self._request_gemini_content(
                        user_message,
                        model_name=self._resolve_gemini_model_name(),
                    )
                raise requests.HTTPError(
                    "Falha ao acessar Ollama. O endpoint /api/chat retornou 404 e o fallback "
                    f"/api/generate também falhou em {self.base_url}."
                ) from fallback_exc
        except requests.RequestException:
            # Se Ollama falhar e houver chave Gemini, tenta Gemini automaticamente.
            if self.gemini_api_key:
                return self._request_gemini_content(
                    user_message,
                    model_name=self._resolve_gemini_model_name(),
                )
            raise

    def _resolve_gemini_model_name(self) -> str:
        model_hint = self._normalize_gemini_model_name(self.model).lower()
        if model_hint.startswith("gemini"):
            return self._normalize_gemini_model_name(self.model)
        return self._normalize_gemini_model_name(self.gemini_model)

    @staticmethod
    def _normalize_gemini_model_name(model_name: str) -> str:
        normalized = str(model_name or "").strip()
        if normalized.startswith("models/"):
            normalized = normalized[len("models/"):]

        legacy_aliases = {
            "gemini-1.5-flash": "gemini-2.5-flash",
            "gemini-1.5-pro": "gemini-2.5-pro",
        }
        return legacy_aliases.get(normalized, normalized)

    _GEMINI_MAX_RETRIES = 4
    _GEMINI_RETRY_BASE_DELAY = 2  # seconds
    _GEMINI_RETRYABLE_STATUS_CODES = {429, 500, 502, 503}

    def _request_gemini_content(self, user_message: str, model_name: str | None = None) -> str:
        if not self.gemini_api_key:
            raise ValueError("GEMINI_API_KEY não configurado para o provedor Gemini.")

        resolved_model = str(model_name or self._resolve_gemini_model_name()).strip()
        if not resolved_model:
            resolved_model = "gemini-2.5-flash"

        endpoints = [
            f"https://generativelanguage.googleapis.com/v1beta/models/{resolved_model}:generateContent",
            f"https://generativelanguage.googleapis.com/v1/models/{resolved_model}:generateContent",
        ]
        model_candidates = [resolved_model]
        if resolved_model == "gemini-2.5-flash":
            model_candidates.append("gemini-2.0-flash")

        last_error: Exception | None = None
        for candidate_model in model_candidates:
            for endpoint in endpoints:
                current_endpoint = endpoint.replace(f"/{resolved_model}:", f"/{candidate_model}:")
                result = self._gemini_post_with_retry(current_endpoint, user_message, candidate_model)
                if result is not None:
                    return result

        # Todas as combinações falharam.
        if last_error is not None:
            raise ValueError(
                "Não foi possível obter resposta válida do Gemini. "
                f"Modelos tentados: {', '.join(model_candidates)}. "
                "Verifique se a chave tem acesso ao modelo e tente definir GEMINI_MODEL=gemini-2.0-flash."
            ) from last_error
        raise ValueError(
            "Todas as tentativas de chamar a API Gemini falharam. "
            "Isso geralmente indica um erro 400 (Bad Request) persistente "
            "(ex: chave de API expirada ou payload inválido). Verifique os logs do terminal."
        )

    def _gemini_post_with_retry(
        self,
        endpoint: str,
        user_message: str,
        candidate_model: str,
    ) -> str | None:
        """POST to a single Gemini endpoint with retry + exponential backoff.

        Returns the extracted text on success, ``None`` if the endpoint/model
        is unavailable (400/404) so the caller can try the next candidate,
        or raises on non-retryable errors.
        """
        last_exc: Exception | None = None
        for attempt in range(1, self._GEMINI_MAX_RETRIES + 1):
            try:
                response = requests.post(
                    endpoint,
                    json=self._build_gemini_payload(user_message),
                    headers={"x-goog-api-key": self.gemini_api_key},
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                last_exc = exc
                logger.warning(
                    "Gemini request failed (attempt %d/%d, model=%s): %s",
                    attempt, self._GEMINI_MAX_RETRIES, candidate_model, exc,
                )
                if attempt < self._GEMINI_MAX_RETRIES:
                    self._backoff_sleep(attempt)
                continue

            status_code = response.status_code

            # Modelo/endpoint indisponível — tentar próximo candidato.
            if status_code in {400, 404}:
                error_text = response.text.strip()
                if "API key expired" in error_text or "API_KEY_INVALID" in error_text:
                    raise ValueError(
                        "CHAVE DE API DO GEMINI EXPIRADA OU INVÁLIDA! "
                        "Acesse https://aistudio.google.com/app/apikey para gerar uma nova "
                        "e atualize a variável GEMINI_API_KEY no arquivo .env."
                    )
                logger.info(
                    "Gemini endpoint retornou %d para model=%s, erro: %s. Tentando próximo...",
                    status_code, candidate_model, error_text[:300],
                )
                return None

            # Rate limit ou erro de servidor — retry com backoff.
            if status_code in self._GEMINI_RETRYABLE_STATUS_CODES:
                delay = self._backoff_delay(attempt)
                logger.warning(
                    "Gemini retornou %d (attempt %d/%d, model=%s). "
                    "Aguardando %.1fs antes de tentar novamente...",
                    status_code, attempt, self._GEMINI_MAX_RETRIES,
                    candidate_model, delay,
                )
                if attempt < self._GEMINI_MAX_RETRIES:
                    time.sleep(delay)
                    continue
                # Última tentativa — cai no raise abaixo.

            # Sucesso
            if response.ok:
                data: dict[str, Any] = response.json()
                candidates = data.get("candidates") or []

                # Resposta vazia — pode ser filtro de conteúdo ou safety block.
                if not candidates:
                    block_reason = (
                        data.get("promptFeedback", {}).get("blockReason", "")
                    )
                    logger.warning(
                        "Gemini retornou 0 candidates (attempt %d/%d, model=%s). "
                        "blockReason=%s, promptFeedback=%s",
                        attempt, self._GEMINI_MAX_RETRIES, candidate_model,
                        block_reason, data.get("promptFeedback"),
                    )
                    # Retry — às vezes é intermitente.
                    if attempt < self._GEMINI_MAX_RETRIES:
                        self._backoff_sleep(attempt)
                        continue
                    # Esgotou retries, retorna vazio para a mensagem correta.
                    return ""

                parts = candidates[0].get("content", {}).get("parts") or []
                texts = [str(part.get("text", "")) for part in parts if part.get("text")]
                result_text = "\n".join(texts).strip()

                # Texto vazio mesmo com candidates presentes.
                if not result_text:
                    finish_reason = candidates[0].get("finishReason", "")
                    logger.warning(
                        "Gemini retornou texto vazio (attempt %d/%d, model=%s, "
                        "finishReason=%s).",
                        attempt, self._GEMINI_MAX_RETRIES, candidate_model,
                        finish_reason,
                    )
                    if attempt < self._GEMINI_MAX_RETRIES:
                        self._backoff_sleep(attempt)
                        continue

                return result_text

            # Erro não-retryável (401, 403, etc.)
            error_text = response.text.strip()
            raise ValueError(
                "Falha ao chamar Gemini API. "
                f"status={status_code}, model={candidate_model}, "
                f"endpoint={endpoint}, detalhe={error_text[:500]}"
            )

        # Esgotou todas as tentativas de retry.
        raise ValueError(
            f"Gemini API indisponível após {self._GEMINI_MAX_RETRIES} tentativas "
            f"(model={candidate_model}, endpoint={endpoint}). "
            f"Último erro: {last_exc}"
        )

    def _backoff_delay(self, attempt: int) -> float:
        """Exponential backoff: 2s, 4s, 8s, 16s."""
        return float(self._GEMINI_RETRY_BASE_DELAY * (2 ** (attempt - 1)))

    def _backoff_sleep(self, attempt: int) -> None:
        time.sleep(self._backoff_delay(attempt))

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
            "systemInstruction": {
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
            "safetySettings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ],
        }

    @staticmethod
    def _format_files(
        files: dict[str, str],
        max_chars_per_file: int = 3_000,
        max_total_chars: int = 15_000,
    ) -> str:
        """Render files as fenced code blocks for the prompt."""
        if not files:
            return "(no source files found)"

        parts: list[str] = []
        used_chars = 0
        omitted_files = 0

        for path, content in files.items():
            if used_chars >= max_total_chars:
                omitted_files += 1
                continue

            truncated = content[:max_chars_per_file]
            if len(content) > max_chars_per_file:
                truncated += "\n... [truncated]"

            block = f"### `{path}`\n```\n{truncated}\n```"
            remaining_chars = max_total_chars - used_chars

            if len(block) > remaining_chars:
                # Mantém a estrutura do bloco e ajusta só o conteúdo final.
                code_header = f"### `{path}`\n```\n"
                code_footer = "\n```"
                available_for_content = remaining_chars - len(code_header) - len(code_footer)

                if available_for_content <= 0:
                    omitted_files += 1
                    continue

                adjusted = truncated[:available_for_content]
                if adjusted != truncated and not adjusted.endswith("\n... [truncated]"):
                    suffix = "\n... [truncated]"
                    if len(adjusted) > len(suffix):
                        adjusted = adjusted[: len(adjusted) - len(suffix)] + suffix
                    else:
                        adjusted = adjusted[:available_for_content]
                block = f"{code_header}{adjusted}{code_footer}"

            parts.append(block)
            used_chars += len(block)

        if omitted_files:
            parts.append(f"... [{omitted_files} arquivo(s) omitido(s) para manter o prompt enxuto]")

        return "\n\n".join(parts)

    @staticmethod
    def _parse_json_response(content: str) -> dict:
        # Strip BOM and surrounding whitespace.
        cleaned = content.strip().lstrip("\ufeff")

        # 1. Try direct parse first.
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # 2. Strip markdown code fences (```json ... ``` or ``` ... ```).
        md_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", cleaned, re.DOTALL)
        if md_match:
            try:
                return json.loads(md_match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # 3. Extract first JSON object from surrounding text.
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise json.JSONDecodeError(
                "No JSON object found in response", cleaned, 0,
            )

        candidate = cleaned[start : end + 1]
        # Remove trailing commas before } or ] (common LLM mistake).
        candidate = re.sub(r",\s*([}\]])", r"\1", candidate)

        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            # 4. Last resort: try fixing common issues (unescaped newlines in strings).
            sanitized = candidate.replace("\r\n", "\\n").replace("\r", "\\n")
            # Only replace actual newlines inside string values, not structural ones.
            # This is a best-effort heuristic.
            try:
                return json.loads(sanitized)
            except json.JSONDecodeError:
                logger.error(
                    "Failed to parse JSON response from LLM. "
                    "Raw content (first 500 chars): %s",
                    content[:500],
                )
                raise
