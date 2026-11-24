"""
Who may use the app, and with which role. An identity is let in only if its
email is in ADMIN_EMAILS, ALLOWED_EMAILS, or was added by an admin. With
SIGNUP_MODE=request, anyone with a verified Google account can ask for
access, and an admin approves or rejects the request.
"""
import hashlib
import re
import time
from dataclasses import dataclass

from core import db, notify
from core.errors import AccessDenied
from core.settings import get_settings

ROLES = ("user", "admin")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Above this many pending requests, new ones are refused, so scripted
# sign-ins can't bury real requests or grow the table without limit.
MAX_PENDING_REQUESTS = 100


class NotInvited(AccessDenied):
    """A verified identity that isn't on the list yet: the one case that may request access."""

    def __init__(self, email: str):
        super().__init__(f"{email} isn't on this app's invite list. Ask the app's admin to add you.")
        self.email = email


@dataclass(frozen=True)
class User:
    # Folder names and quota rows use this id, so emails never appear in paths.
    id: str
    email: str
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


# The only identity when AUTH_MODE=off (the app on your own computer).
LOCAL_USER = User(id="local", email="local", role="admin")


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def user_id_for(email: str) -> str:
    return hashlib.sha256(normalize_email(email).encode()).hexdigest()[:16]


def _db_role(email: str):
    with db.connect() as con:
        row = con.execute("SELECT role FROM users WHERE email = ?", (email,)).fetchone()
    return row["role"] if row else None


def _check_identity(email: str, sub):
    """
    Bind an email to the Google account (its permanent `sub` id) that first
    signed in with it. If the address is ever re-registered by someone else,
    for example a reassigned work address, the newcomer doesn't inherit the
    original owner's meetings and role.
    """
    if not sub:
        return
    with db.connect() as con:
        row = con.execute("SELECT sub FROM identities WHERE email = ?", (email,)).fetchone()
        if row is None:
            con.execute("INSERT INTO identities (email, sub, first_seen) VALUES (?, ?, ?)",
                        (email, str(sub), time.time()))
        elif row["sub"] != str(sub):
            raise AccessDenied(
                f"{email} belongs to a different Google account than the one first used with "
                "this app. Ask the app's admin to check your access."
            )


def authorize(email, email_verified, sub=None) -> User:
    """
    Decide whether a signed-in identity may use the app. Called on every
    rerun, so removing a user takes effect at their next click.
    """
    email = normalize_email(email)
    if not email:
        raise AccessDenied("Your sign-in didn't include an email address.")
    # Google sets email_verified; an unverified address could belong to anyone.
    if email_verified not in (True, "true", "True", 1):
        raise AccessDenied("Your email address isn't verified with your sign-in provider.")

    settings = get_settings()
    if email in settings.admin_emails:
        role = "admin"
    else:
        role = _db_role(email) or ("user" if email in settings.allowed_emails else None)
    if role is None:
        raise NotInvited(email)
    _check_identity(email, sub)
    return User(id=user_id_for(email), email=email, role=role)


def _require_admin(actor: User):
    # Checked here, not only by hiding the admin page, so no UI path can skip it.
    if not actor.is_admin:
        raise PermissionError("Only admins can manage users.")


def list_users(actor: User) -> list:
    _require_admin(actor)
    settings = get_settings()
    rows = {}
    for email in settings.allowed_emails:
        rows[email] = {"email": email, "role": "user", "source": "ALLOWED_EMAILS", "added_by": "", "added_at": None}
    with db.connect() as con:
        for r in con.execute("SELECT email, role, added_by, added_at FROM users"):
            rows[r["email"]] = {**dict(r), "source": "app"}
    for email in settings.admin_emails:
        rows[email] = {"email": email, "role": "admin", "source": "ADMIN_EMAILS", "added_by": "", "added_at": None}
    return sorted(rows.values(), key=lambda r: (r["role"] != "admin", r["email"]))


def add_user(actor: User, email: str, role: str = "user", send_invite: bool = False):
    """Give email access. With send_invite, a newly added person is told by email."""
    _require_admin(actor)
    email = normalize_email(email)
    if not EMAIL_RE.fullmatch(email):
        raise ValueError("Enter a valid email address.")
    if role not in ROLES:
        raise ValueError(f"Role must be one of {', '.join(ROLES)}.")
    if email in get_settings().admin_emails:
        raise ValueError(f"{email} is already an admin through ADMIN_EMAILS.")
    with db.connect() as con:
        is_new = con.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone() is None
        con.execute(
            "INSERT INTO users (email, role, added_by, added_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(email) DO UPDATE SET role = excluded.role",
            (email, role, actor.email, time.time()),
        )
        # Adding someone settles any request they had open.
        con.execute("DELETE FROM access_requests WHERE email = ?", (email,))
    db.audit("user_added", actor, detail=f"{email} as {role}")
    if send_invite and is_new:
        notify.invited(email, role)
    return is_new


def remove_user(actor: User, email: str):
    """Revoke access. The user's meetings stay on disk until deleted by hand."""
    _require_admin(actor)
    email = normalize_email(email)
    if email == actor.email:
        raise ValueError("You can't remove yourself.")
    settings = get_settings()
    if email in settings.admin_emails or email in settings.allowed_emails:
        raise ValueError(
            f"{email} is set in ADMIN_EMAILS or ALLOWED_EMAILS. Remove it there and restart the app."
        )
    with db.connect() as con:
        removed = con.execute("DELETE FROM users WHERE email = ?", (email,)).rowcount
    if not removed:
        raise ValueError(f"{email} isn't in the user list.")
    db.audit("user_removed", actor, detail=email)


# Access requests (SIGNUP_MODE=request)

def request_status(email: str):
    """'pending', 'rejected', or None if this email never asked."""
    with db.connect() as con:
        row = con.execute("SELECT status FROM access_requests WHERE email = ?",
                          (normalize_email(email),)).fetchone()
    return row["status"] if row else None


NAME_MAX = 80
REASON_MAX = 300


def _clean(text, limit: int) -> str:
    """Registration text is shown to admins and put in emails: one line, no control characters."""
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(text or ""))
    return re.sub(r"\s+", " ", text).strip()[:limit]


def request_access(email: str, sub=None, name: str = None, reason: str = None):
    """
    Record a registration from a signed-in, verified identity. Only reachable
    after authorize() raised NotInvited, which happens after the
    email_verified check, so unverified addresses can't get here.
    """
    email = normalize_email(email)
    name, reason = _clean(name, NAME_MAX), _clean(reason, REASON_MAX)
    with db.connect() as con:
        if con.execute("SELECT 1 FROM access_requests WHERE email = ?", (email,)).fetchone():
            return   # one request per email; a rejection stays rejected
        pending = con.execute("SELECT COUNT(*) FROM access_requests WHERE status = 'pending'").fetchone()[0]
        if pending >= MAX_PENDING_REQUESTS:
            raise ValueError("The app isn't taking new requests right now. Try again later.")
        con.execute(
            "INSERT INTO access_requests (email, sub, status, requested_at, name, reason) "
            "VALUES (?, ?, 'pending', ?, ?, ?)",
            (email, str(sub) if sub else None, time.time(), name or None, reason or None),
        )
    db.audit("access_requested", email=email)
    notify.new_access_request(email, name, reason)


def list_requests(actor: User) -> list:
    _require_admin(actor)
    with db.connect() as con:
        rows = con.execute(
            "SELECT email, name, reason, requested_at FROM access_requests "
            "WHERE status = 'pending' ORDER BY requested_at"
        ).fetchall()
    return [dict(r) for r in rows]


def pending_request_count() -> int:
    with db.connect() as con:
        return con.execute("SELECT COUNT(*) FROM access_requests WHERE status = 'pending'").fetchone()[0]


def approve_request(actor: User, email: str):
    _require_admin(actor)
    email = normalize_email(email)
    if request_status(email) != "pending":
        raise ValueError(f"{email} has no pending request.")
    with db.connect() as con:
        req = con.execute("SELECT name FROM access_requests WHERE email = ?", (email,)).fetchone()
        account = con.execute("SELECT name FROM local_accounts WHERE email = ?", (email,)).fetchone()
    add_user(actor, email, "user")   # also clears the request
    db.audit("request_approved", actor, detail=email)
    name = (account and account["name"]) or (req and req["name"]) or None
    notify.access_approved(email, name=name, has_password=account is not None)


def reject_request(actor: User, email: str):
    _require_admin(actor)
    email = normalize_email(email)
    with db.connect() as con:
        changed = con.execute(
            "UPDATE access_requests SET status = 'rejected', decided_by = ?, decided_at = ? "
            "WHERE email = ? AND status = 'pending'",
            (actor.email, time.time(), email),
        ).rowcount
    if not changed:
        raise ValueError(f"{email} has no pending request.")
    db.audit("request_rejected", actor, detail=email)
