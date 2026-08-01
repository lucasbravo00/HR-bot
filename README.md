# 🧭 People Ops Copilot

An AI recruiting assistant designed as **decision support** for the recruiter — not as an
automated decision-maker. Every model recommendation is backed by evidence quoted
verbatim from the resume, and the final score is computed in code, deterministically
and auditably.

## How it works (MVP 1 — recruiting core)

1. **Job description → rubric.** The AI extracts a competency rubric (technical, soft
   skills, languages) with weights, evidence criteria and must-have requirements — in
   the style of a structured interview. The recruiter **edits it** before evaluating:
   the rubric belongs to the human, not the model.
2. **Resume → evidence-based evaluation.** Each resume (PDF or text) is evaluated
   **independently** against the rubric. Per competency, the model returns one of three
   states — *evidence found*, *partial evidence* or *no evidence* — along with
   **verbatim quotes** from the resume and a brief justification. "No evidence" means
   the resume doesn't mention it, not that the candidate lacks the competency.
3. **Ranking computed in code.** The score is a deterministic weighted sum of the
   per-competency judgments (`core/scoring.py`). The LLM never generates the number:
   it judges evidence; the arithmetic is reproducible and auditable.

### Responsible-design decisions

- **Human-in-the-loop**: the tool informs, the recruiter decides. The rubric is
  editable and every report exposes the full reasoning for review.
- **No magic numbers**: the model is never asked for a "% match" (LLMs produce
  apparent precision without substance). The score comes from recruiter-defined weights.
- **Independent evaluation**: each candidate is judged against the rubric, never
  compared with other candidates (avoids ordering effects).
- **Synthetic data**: the resumes in `sample_data/` are fictional. Never push real
  resumes to a repository.

Regulation is moving in this direction: the EU AI Act classifies AI systems for
recruitment as high-risk, and rules like NYC Local Law 144 require audits of automated
hiring tools.

## AI engines: cloud or local open source

The LLM layer is abstracted behind a common interface (`core/providers/`), with two
engines switchable from the sidebar:

| | **Claude (Anthropic)** | **Ollama (local, open source)** |
|---|---|---|
| Privacy | Resumes travel to the API | 🔒 Resumes never leave your machine |
| Cost | Pay per token | Free (runs on your hardware) |
| Evidence-judgment quality | High | Model-dependent (Llama 3.1 8B is noticeably less precise) |
| PDFs | Native document reading | Local text extraction (`pypdf`); can't read scans |
| Structured output | Guaranteed by the API | Ollama constrained decoding + Pydantic validation with retry |

The local option matters for HR: resumes are sensitive personal data, and being able to
process everything on-premise is a real requirement in many organizations. The design
mitigates the local model's lower quality: the rubric is always recruiter-editable, and
the score is computed in code — the local model only contributes evidence judgments,
which the report exposes with quotes for human review.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Option A — Claude (recommended for quality):
export ANTHROPIC_API_KEY="your-api-key"   # or authenticate with `ant auth login`

# Option B — local open-source model (no API key):
#   1. Install Ollama: https://ollama.com
#   2. ollama pull llama3.1

.venv/bin/streamlit run app.py
```

For a quick tour: create a job by pasting `sample_data/job_customer_success.txt` and
upload the three synthetic resumes from `sample_data/` (strong, medium and weak fit).

Job descriptions in any language work: the prompts instruct the model to write the
rubric and reports in the language of the job description.

## Stack

- **Python + Anthropic API** (`claude-opus-4-8`) with structured outputs
  (`messages.parse` + Pydantic), prompt caching on the per-job context, and native
  PDF reading.
- **Ollama** as the alternative local open-source engine (Llama 3.1 by default,
  configurable), with structured output via JSON Schema.
- **Streamlit** for the UI, **SQLite** for persistence.

## Project layout

```
app.py                    # Streamlit UI (engine selector included)
core/models.py            # Pydantic schemas (rubric, evaluations)
core/prompts.py           # Prompts shared across engines
core/llm.py               # Provider facade
core/providers/base.py    # Common interface (LLMProvider) and LLMError
core/providers/claude.py  # Claude engine (Anthropic API)
core/providers/ollama.py  # Local open-source engine (Ollama)
core/scoring.py           # Deterministic scoring + missing must-have detection
core/db.py                # SQLite persistence
sample_data/              # Synthetic demo job description and resumes
```

## Roadmap

- **MVP 2**: blind screening (resume anonymization before evaluation), behavioral
  (STAR) interview questions generated from detected gaps, pre-interview executive
  summary, invitation/rejection/follow-up emails, recruiter decision log, test-retest
  consistency checks of evaluations.
- **MVP 3 (People Ops Copilot)**: job description generator, competency matrices,
  onboarding and development plans — as modules on the same foundation.
