"""SQLite persistence: jobs, evaluated candidates, and their generated artifacts."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "hr_copilot.db"

# Columns added after the initial schema shipped, applied to existing databases.
CANDIDATE_COLUMNS = {
    "blind": "INTEGER NOT NULL DEFAULT 0",
    "interview_kit_json": "TEXT",
    "emails_json": "TEXT",
    "onboarding_plan_json": "TEXT",
}


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
    for name, ddl in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def init_db() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                jd_text TEXT NOT NULL,
                rubric_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                filename TEXT NOT NULL,
                evaluation_json TEXT NOT NULL,
                score REAL NOT NULL,
                missing_must_haves_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            -- Standalone copilot artifacts (job descriptions, competency matrices).
            -- One table keyed by kind, so new modules need no schema change.
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        _ensure_columns(conn, "candidates", CANDIDATE_COLUMNS)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ------------------------------------------------------------------ jobs

def create_job(title: str, jd_text: str, rubric_json: str) -> int:
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO jobs (title, jd_text, rubric_json, created_at) VALUES (?, ?, ?, ?)",
            (title, jd_text, rubric_json, _now()),
        )
        return cur.lastrowid


def list_jobs() -> list[sqlite3.Row]:
    with _conn() as conn:
        return conn.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()


def get_job(job_id: int) -> sqlite3.Row | None:
    with _conn() as conn:
        return conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()


def update_rubric(job_id: int, rubric_json: str) -> None:
    with _conn() as conn:
        conn.execute("UPDATE jobs SET rubric_json = ? WHERE id = ?", (rubric_json, job_id))


def delete_job(job_id: int) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))


# ------------------------------------------------------------------ candidates

def add_candidate(
    job_id: int,
    name: str,
    filename: str,
    evaluation_json: str,
    score: float,
    missing_must_haves: list[str],
    blind: bool = False,
) -> int:
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO candidates
               (job_id, name, filename, evaluation_json, score,
                missing_must_haves_json, blind, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job_id,
                name,
                filename,
                evaluation_json,
                score,
                json.dumps(missing_must_haves),
                int(blind),
                _now(),
            ),
        )
        return cur.lastrowid


def list_candidates(job_id: int) -> list[sqlite3.Row]:
    with _conn() as conn:
        return conn.execute(
            "SELECT * FROM candidates WHERE job_id = ? ORDER BY score DESC", (job_id,)
        ).fetchall()


def candidate_filenames(job_id: int) -> set[str]:
    with _conn() as conn:
        rows = conn.execute("SELECT filename FROM candidates WHERE job_id = ?", (job_id,)).fetchall()
        return {r["filename"] for r in rows}


def delete_candidate(candidate_id: int) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM candidates WHERE id = ?", (candidate_id,))


# ------------------------------------------------------------------ artifacts

def save_interview_kit(candidate_id: int, kit_json: str) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE candidates SET interview_kit_json = ? WHERE id = ?", (kit_json, candidate_id)
        )


def save_onboarding_plan(candidate_id: int, plan_json: str) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE candidates SET onboarding_plan_json = ? WHERE id = ?",
            (plan_json, candidate_id),
        )


def save_email(candidate_id: int, kind: str, subject: str, body: str) -> None:
    """Store one draft per email kind, replacing any previous draft of that kind."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT emails_json FROM candidates WHERE id = ?", (candidate_id,)
        ).fetchone()
        emails = json.loads(row["emails_json"]) if row and row["emails_json"] else {}
        emails[kind] = {"subject": subject, "body": body}
        conn.execute(
            "UPDATE candidates SET emails_json = ? WHERE id = ?",
            (json.dumps(emails), candidate_id),
        )


# ------------------------------------------------------------------ documents

def save_document(kind: str, title: str, payload_json: str) -> int:
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO documents (kind, title, payload_json, created_at) VALUES (?, ?, ?, ?)",
            (kind, title, payload_json, _now()),
        )
        return cur.lastrowid


def list_documents(kind: str) -> list[sqlite3.Row]:
    with _conn() as conn:
        return conn.execute(
            "SELECT * FROM documents WHERE kind = ? ORDER BY created_at DESC", (kind,)
        ).fetchall()


def get_document(document_id: int) -> sqlite3.Row | None:
    with _conn() as conn:
        return conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()


def delete_document(document_id: int) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
