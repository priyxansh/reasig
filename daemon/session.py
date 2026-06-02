"""
ReaSig — Session Persistence via SQLite

Saves/loads per-project conversation history into a single SQLite database.
Uses stdlib sqlite3.

Schema
------
sessions(id, project_path UNIQUE, created_at, updated_at)
messages(id, session_id FK, role, content, created_at)
"""

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("reasig.session")

MAX_HISTORY_PAIRS = 50   # max user+assistant turn pairs stored per project
_DB_DIR  = Path.home() / ".config" / "reasig"
_DB_PATH = _DB_DIR / "reasig.db"


# ── Helpers ────────────────────────────────────────────────────────────────

def _normalise_path(project_path: str) -> str:
    """Return a stable DB key."""
    return project_path.strip() or "__unsaved__"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    """Open (and auto-initialise) the SQLite database, return a connection."""
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")    # safe concurrent reads
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            project_path TEXT    NOT NULL UNIQUE,
            created_at   TEXT    NOT NULL,
            updated_at   TEXT    NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            role       TEXT    NOT NULL CHECK(role IN ('user', 'assistant')),
            content    TEXT    NOT NULL,
            created_at TEXT    NOT NULL
        );
    """)
    conn.commit()
    return conn


# ── Public API ─────────────────────────────────────────────────────────────

def load_history(project_path: str) -> list[dict]:
    """Return stored conversation turns for *project_path* ([] if none).

    Safe to call from asyncio.to_thread().
    """
    key = _normalise_path(project_path)
    try:
        conn = _connect()
        with conn:
            row = conn.execute(
                "SELECT id FROM sessions WHERE project_path = ?", (key,)
            ).fetchone()
            if not row:
                return []
            rows = conn.execute(
                "SELECT role, content FROM messages "
                "WHERE session_id = ? ORDER BY id ASC",
                (row["id"],),
            ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in rows]
    except Exception as exc:
        logger.warning("Could not load session for '%s': %s", key, exc)
        return []


def save_history(project_path: str, history: list[dict]) -> None:
    """Persist *history* for *project_path*, trimming to MAX_HISTORY_PAIRS.

    Uses DELETE + bulk INSERT (not individual UPDATEs) so every save is an
    atomic replace.  Safe to call from asyncio.to_thread().
    """
    key = _normalise_path(project_path)

    # Keep only the most recent N pairs
    max_entries = MAX_HISTORY_PAIRS * 2
    if len(history) > max_entries:
        history = history[-max_entries:]

    # Filter out any malformed entries defensively
    history = [h for h in history if "role" in h and "content" in h]

    try:
        conn = _connect()
        now = _now()
        with conn:
            # Upsert the session row
            conn.execute(
                """
                INSERT INTO sessions (project_path, created_at, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(project_path) DO UPDATE SET updated_at = excluded.updated_at
                """,
                (key, now, now),
            )
            session_id = conn.execute(
                "SELECT id FROM sessions WHERE project_path = ?", (key,)
            ).fetchone()["id"]

            # Atomic replace of all stored messages
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            conn.executemany(
                "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                [(session_id, h["role"], h["content"], now) for h in history],
            )
        logger.debug(
            "Session saved for '%s' (%d messages / %d turns)",
            key, len(history), len(history) // 2,
        )
    except Exception as exc:
        logger.warning("Could not save session for '%s': %s", key, exc)


def clear_history(project_path: str) -> None:
    """Delete all stored messages for *project_path* (keeps the session row).

    Called when the user clicks the Clear button in the UI.
    Safe to call from asyncio.to_thread().
    """
    key = _normalise_path(project_path)
    try:
        conn = _connect()
        with conn:
            row = conn.execute(
                "SELECT id FROM sessions WHERE project_path = ?", (key,)
            ).fetchone()
            if row:
                conn.execute("DELETE FROM messages WHERE session_id = ?", (row["id"],))
        logger.debug("Session cleared for '%s'", key)
    except Exception as exc:
        logger.warning("Could not clear session for '%s': %s", key, exc)


def has_history(project_path: str) -> bool:
    """Return True if there are any stored messages for *project_path*."""
    key = _normalise_path(project_path)
    try:
        conn = _connect()
        with conn:
            row = conn.execute(
                "SELECT id FROM sessions WHERE project_path = ?", (key,)
            ).fetchone()
            if not row:
                return False
            count = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE session_id = ?", (row["id"],)
            ).fetchone()[0]
        return count > 0
    except Exception as exc:
        logger.warning("Could not check history for '%s': %s", key, exc)
        return False
