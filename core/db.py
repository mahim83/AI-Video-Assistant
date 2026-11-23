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
"""

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
