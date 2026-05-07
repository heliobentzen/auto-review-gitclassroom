# auto-review-gitclassroom

Ferramenta de correcao automatizada para atividades do GitHub Classroom, com suporte a:

1. Execucao em CLI.
2. Fluxo Web com pre-visualizacao, revisao manual e publicacao de issues.

Para cada submissao, a ferramenta pode:

1. Ler metadados da atividade no Classroom.
2. Buscar codigo no repositorio do aluno.
3. Gerar feedback estruturado com modelo local via Ollama.
4. Publicar issue por aluno com o feedback.
5. Exportar relatorio CSV de notas.

## Requisitos

1. Python 3.10+.
2. Token GitHub com escopo repo e acesso ao Classroom.
3. Ollama instalado e em execucao.
4. Modelo Ollama ja baixado (exemplo: qwen2.5-coder:7b).

## Instalacao

```bash
git clone https://github.com/heliobentzen/auto-review-gitclassroom.git
cd auto-review-gitclassroom

python -m venv .venv

# Linux/macOS
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1

# Windows cmd
.venv\Scripts\activate.bat

python -m pip install --upgrade pip
pip install -r requirements.txt

ollama pull qwen2.5-coder:7b
```

## Configuracao

Crie um arquivo .env com:

```env
GITHUB_TOKEN=ghp_seu_token
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen2.5-coder:7b
GEMINI_API_KEY=your_gemini_api_key_here
```

Observacoes:

1. OLLAMA_HOST e opcional (padrao local).
2. OLLAMA_MODEL e opcional (sobrescreve padrao da aplicacao).
3. GEMINI_API_KEY e obrigatória apenas ao usar modelos Gemini no campo --model (ex.: gemini-2.0-flash).

## Uso via CLI

```bash
python -m src.main --assignment-id <ID_OU_URL> [opcoes]
```

Argumentos principais:

1. --assignment-id: ID numerico ou URL da assignment do Classroom.
2. --output: caminho do CSV (padrao: reports/grade_report.csv).
3. --extensions: extensoes de arquivo para revisar.
4. --model: modelo Ollama para revisao.
5. --instruction: instrucao textual do professor.
6. --dry-run: nao cria issue, apenas simula avaliacao.

Exemplos:

```bash
python -m src.main --assignment-id 12345
python -m src.main --assignment-id https://classroom.github.com/classrooms/260986872-ifpepalmares-mobile-3a/assignments/atividade-de-navega-o-de-telas
python -m src.main --assignment-id 12345 --dry-run
python -m src.main --assignment-id 12345 --instruction "Avaliar navegacao entre telas" --dry-run
```

## Uso via Web

```bash
python -m src.webapp
```

Abra:

```text
http://127.0.0.1:8000
```

Fluxo recomendado:

1. Informar URL (ou ID) da assignment.
2. Informar instrucoes da atividade.
3. Selecionar nivel de analise.
4. Iniciar previa e acompanhar progresso.
5. Revisar/editar comentarios por aluno.
6. Salvar para publicar issues.

Durante a publicacao, a interface exibe resumo de auditoria:

1. created: issues criadas.
2. skipped: ignoradas (fora do job, sem payload, ja publicadas).
3. failed: falhas de criacao por aluno.

## Saidas

1. CSV com colunas: student, repository, grade, grade_comment, issue_url.
2. Issue no repositorio do aluno com secoes:
   - Resumo
   - Problemas Encontrados
   - Melhorias Sugeridas

## Arquitetura (visao geral)

1. src/config.py: configuracao centralizada por variavel de ambiente.
2. src/classroom_client.py: cliente REST do GitHub Classroom.
3. src/github_client.py: leitura de arquivos e criacao de issue via PyGithub.
4. src/reviewer.py: integracao com Ollama e parsing de resposta.
5. src/reporter.py: consolidacao e exportacao CSV.
6. src/main.py: orquestracao da CLI.
7. src/webapp.py: fluxo web, jobs em memoria e publicacao manual.

## Dependencias principais

1. PyGithub>=2.9.1
2. python-dotenv>=1.1.0
3. requests>=2.32.3
4. Flask>=3.1.1
5. pytest>=8.4.2

## Testes

```bash
pytest
```

Ou sem ativar ambiente:

```bash
.venv\Scripts\python -m pytest
```

## Estrutura do projeto

```text
auto-review-gitclassroom/
├── src/
│   ├── __init__.py
│   ├── classroom_client.py
│   ├── config.py
│   ├── github_client.py
│   ├── main.py
│   ├── reporter.py
│   ├── reviewer.py
│   └── webapp.py
├── tests/
│   ├── __init__.py
│   ├── test_classroom_client.py
│   ├── test_github_client.py
│   ├── test_main.py
│   ├── test_reporter.py
│   ├── test_reviewer.py
│   └── test_webapp.py
├── requirements.txt
└── README.md
```
