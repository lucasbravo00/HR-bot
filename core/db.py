"""SQLite persistence: jobs and evaluated candidates."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "hr_copilot.db"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


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
            """
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def add_candidate(
    job_id: int,
    name: str,
    filename: str,
    evaluation_json: str,
    score: float,
    missing_must_haves: list[str],
) -> int:
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO candidates
               (job_id, name, filename, evaluation_json, score, missing_must_haves_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (job_id, name, filename, evaluation_json, score, json.dumps(missing_must_haves), _now()),
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
