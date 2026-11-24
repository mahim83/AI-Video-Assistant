"""
App database (SQLite, in DATA_DIR/app.db): users added by admins, usage
events for quotas, and the audit log. One short-lived connection per call,
so it is safe from Streamlit's per-session threads.
"""
import logging
import os
import sqlite3
import threading
import time
from contextlib import contextmanager

from core.settings import get_settings

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    email    TEXT PRIMARY KEY,
    role     TEXT NOT NULL CHECK (role IN ('admin', 'user')),
    added_by TEXT NOT NULL,
    added_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    ts      REAL NOT NULL,
    user_id TEXT NOT NULL,
    kind    TEXT NOT NULL,
    amount  REAL NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS events_by_user ON events (user_id, kind, ts);
CREATE TABLE IF NOT EXISTS audit (
    ts      REAL NOT NULL,
    user_id TEXT,
    email   TEXT,
    action  TEXT NOT NULL,
    detail  TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS audit_by_ts ON audit (ts);
CREATE TABLE IF NOT EXISTS identities (
    email      TEXT PRIMARY KEY,
    sub        TEXT NOT NULL,
    first_seen REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS access_requests (
    email        TEXT PRIMARY KEY,
    sub          TEXT,
    status       TEXT NOT NULL CHECK (status IN ('pending', 'rejected')),
    requested_at REAL NOT NULL,
    decided_by   TEXT,
    decided_at   REAL
);
-- Email + password accounts (core/local_auth.py). Only a scrypt hash of the
-- password is stored; codes and session tokens are stored as SHA-256 hashes.
CREATE TABLE IF NOT EXISTS local_accounts (
    email         TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at    REAL NOT NULL,
    failed_logins INTEGER NOT NULL DEFAULT 0,
    locked_until  REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS pending_registrations (
    email         TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    reason        TEXT,
    password_hash TEXT NOT NULL,
    created_at    REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS email_codes (
    email      TEXT NOT NULL,
    purpose    TEXT NOT NULL CHECK (purpose IN ('register', 'reset')),
    code_hash  TEXT NOT NULL,
    expires_at REAL NOT NULL,
    attempts   INTEGER NOT NULL DEFAULT 0,
    sent_at    REAL NOT NULL,
    PRIMARY KEY (email, purpose)
);
CREATE TABLE IF NOT EXISTS login_tokens (
    token_hash TEXT PRIMARY KEY,
    email      TEXT NOT NULL,
    expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    email      TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL
);
"""

# Columns added after a table first shipped. CREATE TABLE IF NOT EXISTS
# leaves an existing table alone, so they're added here on startup.
ADDED_COLUMNS = {
    "access_requests": {"name": "TEXT", "reason": "TEXT"},
    "users": {"name": "TEXT"},
}


def _add_missing_columns(con):
    for table, columns in ADDED_COLUMNS.items():
        present = {row[1] for row in con.execute(f"PRAGMA table_info({table})")}
        for column, sql_type in columns.items():
            if column not in present:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}")

_init_lock = threading.Lock()
_initialized = set()   # database paths whose schema exists


def db_path() -> str:
    return os.path.join(get_settings().data_dir, "app.db")


@contextmanager
def connect():
    path = db_path()
    with _init_lock:
        if path not in _initialized:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            con = sqlite3.connect(path)
            try:
                # WAL lets readers (quota checks) run while another session writes.
                con.execute("PRAGMA journal_mode=WAL")
                con.executescript(SCHEMA)
                _add_missing_columns(con)
                con.commit()
            finally:
                con.close()
            _initialized.add(path)

    con = sqlite3.connect(path, timeout=10)
    con.row_factory = sqlite3.Row
    try:
        with con:   # commits on success, rolls back on error
            yield con
    finally:
        con.close()


def record_event(user_id: str, kind: str, amount: float = 1.0):
    with connect() as con:
        con.execute(
            "INSERT INTO events (ts, user_id, kind, amount) VALUES (?, ?, ?, ?)",
            (time.time(), user_id, kind, amount),
        )


def total_since(user_id: str, kind: str, since: float) -> float:
    with connect() as con:
        row = con.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM events WHERE user_id = ? AND kind = ? AND ts >= ?",
            (user_id, kind, since),
        ).fetchone()
    return float(row[0])


def totals_since(since: float) -> dict:
    """{user_id: {kind: total}} for every user with events since `since`."""
    with connect() as con:
        rows = con.execute(
            "SELECT user_id, kind, SUM(amount) FROM events WHERE ts >= ? GROUP BY user_id, kind",
            (since,),
        ).fetchall()
    out = {}
    for user_id, kind, total in rows:
        out.setdefault(user_id, {})[kind] = total
    return out


def audit(action: str, user=None, detail: str = "", email: str = None):
    """
    Record who did what. Never pass transcript text or questions as `detail`:
    the log is for accountability, not a copy of users' content.
    """
    user_id = getattr(user, "id", None)
    email = email or getattr(user, "email", None)
    try:
        with connect() as con:
            con.execute(
                "INSERT INTO audit (ts, user_id, email, action, detail) VALUES (?, ?, ?, ?, ?)",
                (time.time(), user_id, email, action, detail[:500]),
            )
    except sqlite3.Error:
        # An audit failure must not take the request down with it.
        log.exception("audit write failed: action=%s user=%s", action, user_id)
    log.info("audit action=%s user=%s detail=%s", action, user_id, detail[:200])


def audited_since(action: str, email: str, since: float) -> bool:
    with connect() as con:
        row = con.execute(
            "SELECT 1 FROM audit WHERE action = ? AND email = ? AND ts >= ? LIMIT 1",
            (action, email, since),
        ).fetchone()
    return row is not None


def recent_audit(limit: int = 200) -> list:
    with connect() as con:
        rows = con.execute(
            "SELECT ts, email, action, detail FROM audit ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]
