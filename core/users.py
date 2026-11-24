"""
Who may use the app, and with which role. An identity is let in once its
email is in ADMIN_EMAILS, ALLOWED_EMAILS, or the users table. With
SIGNUP_MODE=open (the default), anyone with a verified email can register and
use the app straight away; the admins get an email about each registration and
can revoke anyone who looks suspicious. A revoked email can't register again
until an admin adds it back. With SIGNUP_MODE=invite, only emails an admin
added get in.
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
# Who added a users row that came from registering, as shown on the Admin page.
SIGNED_UP = "sign-up"


class NotInvited(AccessDenied):
    """A verified identity that isn't on the list yet: the one case that may register."""

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
        if is_revoked(email):
            raise AccessDenied(REVOKED_MESSAGE)
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
            rows[r["email"]] = {**dict(r), "source": SIGNED_UP if r["added_by"] == SIGNED_UP else "app"}
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
        # Adding someone lifts a revocation.
        con.execute("DELETE FROM access_requests WHERE email = ?", (email,))
    db.audit("user_added", actor, detail=f"{email} as {role}")
    if send_invite and is_new:
        notify.invited(email, role)
    return is_new


def remove_user(actor: User, email: str):
    """
    Revoke access, and keep the email from registering again until an admin
    adds it back. The user's meetings stay on disk until deleted by hand.
    """
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
        if removed:
            con.execute(
                "INSERT INTO access_requests (email, status, requested_at, decided_by, decided_at) "
                "VALUES (?, 'rejected', ?, ?, ?) ON CONFLICT(email) DO UPDATE SET "
                "status = 'rejected', decided_by = excluded.decided_by, decided_at = excluded.decided_at",
                (email, time.time(), actor.email, time.time()),
            )
    if not removed:
        raise ValueError(f"{email} isn't in the user list.")
    db.audit("user_removed", actor, detail=email)


# Registration (SIGNUP_MODE=open)
#
# Revocations live in access_requests with status 'rejected', the table the
# older approve-first sign-up used, so people rejected back then stay out.

REVOKED_MESSAGE = "Your access to this app was revoked. Ask the app's admin if you think this is a mistake."


def is_revoked(email: str) -> bool:
    with db.connect() as con:
        row = con.execute("SELECT 1 FROM access_requests WHERE email = ? AND status = 'rejected'",
                          (normalize_email(email),)).fetchone()
    return row is not None


NAME_MAX = 80
REASON_MAX = 300


def _clean(text, limit: int) -> str:
    """Registration text is shown to admins and put in emails: one line, no control characters."""
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(text or ""))
    return re.sub(r"\s+", " ", text).strip()[:limit]


def register(email: str, sub=None, name: str = None, reason: str = None, method: str = "Google") -> User:
    """
    Give a verified identity access as a regular user, and email the admins.
    Only reachable after authorize() raised NotInvited, which happens after the
    email_verified and revocation checks, so unverified or revoked addresses
    can't get here.
    """
    if get_settings().signup_mode != "open":
        raise AccessDenied("This app is by invitation. Ask the app's admin to add you.")
    email = normalize_email(email)
    if is_revoked(email):
        raise AccessDenied(REVOKED_MESSAGE)
    name, reason = _clean(name, NAME_MAX), _clean(reason, REASON_MAX)
    with db.connect() as con:
        # OR IGNORE: a double click registers once and sends one email.
        added = con.execute(
            "INSERT OR IGNORE INTO users (email, role, added_by, added_at) VALUES (?, 'user', ?, ?)",
            (email, SIGNED_UP, time.time()),
        ).rowcount
        # A request left over from the approve-first sign-up is settled now.
        con.execute("DELETE FROM access_requests WHERE email = ? AND status = 'pending'", (email,))
    if added:
        db.audit("user_registered", email=email, detail=method)
        notify.new_registration(email, name, reason, method)
    return authorize(email, True, sub)
