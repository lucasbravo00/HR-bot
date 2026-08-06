# 🧭 People Ops Copilot

An AI assistant for hiring and people operations, designed as **decision support** for
the practitioner — not as an automated decision-maker. Every recommendation is backed by
evidence quoted verbatim from the source, and anything that must be correct is computed
in code rather than trusted to a model.

Three modules, one foundation:

| Module | What it does |
|---|---|
| 🎯 **Recruiting** | Job description → rubric → blind evaluation → ranking → interview kit → emails → onboarding plan |
| 📝 **Job descriptions** | A short brief becomes a posting with honest, proportionate requirements — then feeds straight into a hiring process |
| 📊 **Competency matrices** | Competencies by seniority level, with observable behavior at each step |

## Recruiting

1. **Job description → rubric.** The AI extracts a competency rubric (technical, soft
   skills, languages) with weights, evidence criteria and must-have requirements — in
   the style of a structured interview. The recruiter **edits it** before evaluating:
   the rubric belongs to the human, not the model.
2. **Blind screening.** Before evaluation, identity is split out of the resume: name,
   contact details, location, age and other personal markers are replaced with
   placeholders, while every professional detail is preserved verbatim. The evaluator
   sees only the redacted text; the recruiter still sees who is who.
3. **Resume → evidence-based evaluation.** Each resume (PDF or text) is evaluated
   **independently** against the rubric. Per competency, the model returns one of three
   states — *evidence found*, *partial evidence* or *no evidence* — along with
   **verbatim quotes** and a brief justification. "No evidence" means the resume doesn't
   mention it, not that the candidate lacks the competency.
4. **Ranking computed in code.** The score is a deterministic weighted sum of the
   per-competency judgments (`core/scoring.py`). The LLM never generates the number:
   it judges evidence; the arithmetic is reproducible and auditable.
5. **Interview kit.** A pre-interview brief plus behavioral (STAR) questions built from
   *this* candidate's evidence gaps — grounded in their actual experience, not generic.
   Each question ships with why it matters and what a strong answer sounds like.
6. **Email drafts.** Invitation, rejection and follow-up drafts the recruiter reviews,
   edits and sends themselves. Nothing is ever sent from the app, and internal scores
   and rubric judgments are never disclosed to candidates.
7. **Onboarding plan.** The evidence gathered while hiring becomes the new hire's first
   90 days: what to ramp up on fastest, sequenced from context to supervised delivery to
   independent ownership, with an observable success signal per milestone.

## Job descriptions

A short brief (role, seniority, context, must-haves) becomes a full posting. The
generator is built to counteract the usual failure modes: it never invents salary,
benefits or perks the brief didn't mention; it keeps must-haves to what is genuinely
disqualifying; it writes requirements as observable capability rather than pedigree; and
it avoids gender-coded and culture-fit language that narrows the applicant pool.

Finished drafts download as Markdown, or go straight into a hiring process with one
click — the posting becomes the rubric candidates are scored against.

## Competency matrices

Competencies by seniority level for calibration, career paths and development
conversations. The hard part of a competency matrix is that levels must differ in
**kind**, not intensity — "does X", "does X well", "does X very well" is a useless
matrix. The prompt pushes for real progression in scope, autonomy, complexity and blast
radius, with behavior a manager could actually witness. Matrices can start from an
existing job and download as CSV.

## Responsible-design decisions

- **Human-in-the-loop**: the tool informs, the practitioner decides. The rubric is
  editable and every report exposes the full reasoning for review.
- **No magic numbers**: the model is never asked for a "% match" (LLMs produce
  apparent precision without substance). The score comes from recruiter-defined weights.
- **Independent evaluation**: each candidate is judged against the rubric, never
  compared with other candidates (avoids ordering effects).
- **Blind screening is enforced in code, not trusted to the model.** Models redact
  inconsistently — during development a local model stripped a surname and left the
  first name in place. Every anonymized resume is therefore swept deterministically
  (`core/redaction.py`) for leftover names, emails, phones and URLs, and the resume's
  filename is replaced too, since `cv_ana_garcia.pdf` is itself an identity leak.
- **Blind screening ends where it should.** It protects the ranking stage. Once a
  recruiter is preparing an interview or a ramp-up plan, the candidate is known to them
  and their real name is used again.
- **Gaps are questions, not verdicts.** Missing evidence drives interview questions and
  onboarding priorities — never framed as an established deficiency.
- **Synthetic data**: the resumes in `sample_data/` are fictional. Never push real
  resumes to a repository.

Regulation is moving in this direction: the EU AI Act classifies AI systems for
recruitment as high-risk, and rules like NYC Local Law 144 require audits of automated
hiring tools.

**Known limitation:** blind screening removes personal identifiers, but employer and
university names stay in the resume — they carry real professional signal and removing
them would gut the evidence. Prestige bias is therefore still in play, and worth being
explicit about rather than papering over.

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
mitigates the local model's lower quality: the rubric is always editable, the score is
computed in code, and blind screening is enforced deterministically — the local model
only contributes judgments, which the UI exposes with quotes for human review.

Providers implement a single primitive (a schema-constrained completion), so every task
lives once in `core/tasks.py` and works on any engine.

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

Job descriptions in any language work: the prompts instruct the model to write rubrics,
reports, questions, emails, postings and matrices in the language of the source text.

## Tests

The deterministic parts — scoring, redaction, rendering and level parsing — are covered
by tests. Several redaction cases come from real failures observed against a local model.

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/ -q
```

## Project layout

```
app.py                          # Router: navigation, engine selection, module dispatch
views/recruiting.py             # Jobs, rubrics, evaluation, interview kits, emails, onboarding
views/job_descriptions.py       # Job description generator
views/competency_matrices.py    # Competency matrix builder
views/common.py                 # Engine picker and shared UI helpers
core/models.py                  # Pydantic schemas for every task
core/prompts.py                 # Prompts, shared across engines
core/tasks.py                   # Tasks, written once against the provider interface
core/llm.py                     # Provider facade
core/providers/base.py          # Common interface (one schema-constrained completion)
core/providers/claude.py        # Claude engine (Anthropic API)
core/providers/ollama.py        # Local open-source engine (Ollama)
core/redaction.py               # Deterministic blind-screening safety net
core/scoring.py                 # Deterministic scoring + missing must-have detection
core/pdf.py                     # Local PDF text extraction
core/db.py                      # SQLite persistence
tests/                          # Regression tests for the deterministic pieces
sample_data/                    # Synthetic demo job description and resumes
```

## Roadmap

- Recruiter decision log: what the AI suggested vs. what the human decided.
- Test-retest consistency checks — run the same resume twice and measure agreement.
- Side-by-side engine comparison on the same rubric.
- Development plans and 1:1 feedback prep, built on the competency matrix.
