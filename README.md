# auto-review-gitclassroom

Automated code review and grading tool for **GitHub Classroom** professors.

For each assignment submission the tool will:

1. **Connect** to GitHub Classroom via the REST API and retrieve the assignment
   and all accepted student repositories.
2. **Read** source files from each student repository.
3. **Review** the code with an OpenAI model and produce structured feedback
   (issues found, suggested improvements, grade 0–10).
4. **Create a GitHub issue** in each student's repository containing the
   AI-generated review.
5. **Export a CSV grade report** with the student login, repository, numeric
   grade (0–10 scale), grade comment, and issue URL.

---

## Requirements

- Python ≥ 3.10
- A **GitHub personal access token** with the `repo` scope (required to read
  student repositories and create issues) and access to GitHub Classroom.
- An **OpenAI API key**.

---

## Installation

```bash
# Clone the repository
git clone https://github.com/heliobentzen/auto-review-gitclassroom.git
cd auto-review-gitclassroom

# Create and activate a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

---

## Configuration

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

```
GITHUB_TOKEN=ghp_your_token_here
OPENAI_API_KEY=sk-your_key_here
```

Optionally set `OPENAI_MODEL` to override the default (`gpt-4o-mini`).

---

## Usage

```
python -m src.main --assignment-id <ID> [options]
```

### Required

| Argument | Description |
|---|---|
| `--assignment-id INT` | GitHub Classroom assignment ID |

### Optional

| Argument | Default | Description |
|---|---|---|
| `--output PATH` | `reports/grade_report.csv` | Output CSV path |
| `--extensions EXT …` | common code files | File extensions to review (e.g. `--extensions .py .js`) |
| `--model MODEL` | `gpt-4o-mini` | OpenAI model |
| `--dry-run` | off | Analyse code but **skip** issue creation |

### Example

```bash
# Full run (creates issues + report)
python -m src.main --assignment-id 12345

# Dry run — see grades without creating issues
python -m src.main --assignment-id 12345 --dry-run --output /tmp/grades.csv

# Review only Python files, use GPT-4o
python -m src.main --assignment-id 12345 --extensions .py --model gpt-4o
```

### Finding the assignment ID

1. Open your classroom on <https://classroom.github.com>.
2. Navigate to **Assignments** and open the assignment.
3. The assignment ID is the number at the end of the URL, e.g.
   `https://classroom.github.com/classrooms/123/assignments/`**`12345`**.

---

## Output

### Grade report CSV

The report is saved to `reports/grade_report.csv` (configurable via `--output`):

| student | repository | grade | grade_comment | issue_url |
|---|---|---|---|---|
| alice | org/alice-lab1 | 8.5 | Solid work, minor style issues. | https://… |
| bob | org/bob-lab1 | 6.0 | Missing error handling. | https://… |

### GitHub issues

An issue is created in each student's repository with three sections:

- **Summary** — overall impression
- **Issues Found** — specific problems identified
- **Suggested Improvements** — actionable recommendations

---

## Running tests

```bash
pytest
```

---

## Project structure

```
auto-review-gitclassroom/
├── src/
│   ├── classroom_client.py   # GitHub Classroom REST API client
│   ├── github_client.py      # PyGithub wrapper (file reading + issue creation)
│   ├── reviewer.py           # OpenAI-powered code reviewer
│   ├── reporter.py           # CSV grade report generator
│   └── main.py               # CLI entry point
├── tests/
│   ├── test_classroom_client.py
│   ├── test_github_client.py
│   ├── test_reviewer.py
│   ├── test_reporter.py
│   └── test_main.py
├── .env.example
├── requirements.txt
└── README.md
```
