"""
Who may use the app, and with which role. Invite-only: an identity is let in
only if its email is in ADMIN_EMAILS, ALLOWED_EMAILS, or was added by an admin.
"""
import hashlib
import re
import time
from dataclasses import dataclass

from core import db
from core.errors import AccessDenied
from core.settings import get_settings

ROLES = ("user", "admin")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


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
        raise AccessDenied(
            f"{email} isn't on this app's invite list. Ask the app's admin to add you."
        )
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


def add_user(actor: User, email: str, role: str = "user"):
    _require_admin(actor)
    email = normalize_email(email)
    if not EMAIL_RE.fullmatch(email):
        raise ValueError("Enter a valid email address.")
    if role not in ROLES:
        raise ValueError(f"Role must be one of {', '.join(ROLES)}.")
    if email in get_settings().admin_emails:
        raise ValueError(f"{email} is already an admin through ADMIN_EMAILS.")
    with db.connect() as con:
        con.execute(
            "INSERT INTO users (email, role, added_by, added_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(email) DO UPDATE SET role = excluded.role",
            (email, role, actor.email, time.time()),
        )
    db.audit("user_added", actor, detail=f"{email} as {role}")


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
