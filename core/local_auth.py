"""
Email + password accounts, alongside Google sign-in.

- Passwords are stored only as salted scrypt hashes and checked in constant time.
- An account exists only after its email is verified with a 6-digit code, so
  nobody can register an address they don't control (an admin's included).
- Five wrong passwords lock the account for 15 minutes. Sign-in errors never
  say whether an email has an account.
- Code emails are rate-limited per address and in total.
- A successful sign-in gets a single-use, 2-minute login token. The browser
  trades it at /local-auth/complete (server.py) for an HttpOnly session
  cookie; only SHA-256 hashes of tokens and codes are stored.

Access is still decided by core.users: a new account must be approved by an
admin, exactly like a Google account.
"""
import base64
import hashlib
import hmac
import logging
import re
import secrets
import time

from core import db, notify
from core.errors import UserFacingError
from core.users import EMAIL_RE, NAME_MAX, REASON_MAX, _clean, normalize_email

log = logging.getLogger(__name__)

SESSION_COOKIE = "ava_session"
SESSION_SECONDS = 30 * 24 * 3600
LOGIN_TOKEN_SECONDS = 120
CODE_SECONDS = 15 * 60
CODE_ATTEMPTS = 5
CODE_RESEND_SECONDS = 60
CODES_PER_EMAIL_PER_DAY = 5
CODES_PER_DAY_TOTAL = 200
MAX_FAILED_LOGINS = 5
LOCK_SECONDS = 15 * 60
PASSWORD_MIN, PASSWORD_MAX = 10, 128

# scrypt cost: about 16 MB and 50 ms per hash on a small server.
_N, _R, _P = 2 ** 14, 8, 1

COMMON_PASSWORDS = frozenset("""
password password1 password12 password123 passw0rd 1234567890 12345678910 0123456789
qwertyuiop qwerty12345 1q2w3e4r5t iloveyou12 welcome123 admin12345 letmein123
abcdefghij abcd123456 asdfghjkl1 zxcvbnm123 india12345 sunshine12
""".split())


class AuthError(UserFacingError):
    """A sign-in or registration problem whose message is safe to show."""


# Passwords

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    b64 = lambda b: base64.b64encode(b).decode()
    return f"scrypt${_N}${_R}${_P}${b64(salt)}${b64(digest)}"


def _check_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, digest = stored.split("$")
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt),
                                n=int(n), r=int(r), p=int(p), dklen=len(expected))
    except Exception:
        return False
    return hmac.compare_digest(actual, expected)


# Hashed once at import, so an unknown email costs the same time as a wrong
# password and response times don't reveal which emails have accounts.
_DUMMY_HASH = hash_password(secrets.token_hex(16))


def password_problem(password: str, email: str = ""):
    if len(password) < PASSWORD_MIN:
        return f"Use at least {PASSWORD_MIN} characters."
    if len(password) > PASSWORD_MAX:
        return f"Use at most {PASSWORD_MAX} characters."
    if password.lower() in COMMON_PASSWORDS or len(set(password)) < 4:
        return "That password is too easy to guess. Try a short phrase of several words."
    local = normalize_email(email).split("@")[0]
    if local and len(local) >= 4 and local in password.lower():
        return "Don't use your email address in your password."
    return None


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# Email codes

def _send_code(email: str, purpose: str):
    """Create and email a 6-digit code, within the rate limits."""
    if not notify.enabled():
        raise AuthError("Email sign-up isn't available right now. Use Google instead.")
    now = time.time()
    with db.connect() as con:
        row = con.execute("SELECT sent_at FROM email_codes WHERE email = ? AND purpose = ?",
                          (email, purpose)).fetchone()
        if row and now - row["sent_at"] < CODE_RESEND_SECONDS:
            raise AuthError("A code was just sent. Wait a minute before asking for another.")
    since = now - 86400
    if db.total_since(f"code:{email}", "code_sent", since) >= CODES_PER_EMAIL_PER_DAY:
        raise AuthError("Too many codes for this email today. Try again tomorrow.")
    if db.total_since("all", "code_sent", since) >= CODES_PER_DAY_TOTAL:
        raise AuthError("The app has sent too many codes today. Try again tomorrow or use Google.")

    code = f"{secrets.randbelow(10 ** 6):06d}"
    with db.connect() as con:
        con.execute(
            "INSERT INTO email_codes (email, purpose, code_hash, expires_at, attempts, sent_at) "
            "VALUES (?, ?, ?, ?, 0, ?) ON CONFLICT(email, purpose) DO UPDATE SET "
            "code_hash = excluded.code_hash, expires_at = excluded.expires_at, attempts = 0, sent_at = excluded.sent_at",
            (email, purpose, _sha(f"{purpose}:{email}:{code}"), now + CODE_SECONDS, now),
        )
    db.record_event(f"code:{email}", "code_sent")
    db.record_event("all", "code_sent")
    action = "finish creating your account" if purpose == "register" else "reset your password"
    notify.send(email, f"Your AI Video Assistant code: {code}",
                f"Your code is {code}. Enter it to {action}.\n\n"
                "It expires in 15 minutes. If you didn't ask for it, you can ignore this email.\n")


def _use_code(email: str, purpose: str, code: str):
    code = re.sub(r"\D", "", code or "")
    # The outcome is decided inside the transaction but raised after it: an
    # exception inside `with con` rolls back, which would undo the attempt
    # count and allow unlimited guesses.
    with db.connect() as con:
        row = con.execute("SELECT code_hash, expires_at, attempts FROM email_codes "
                          "WHERE email = ? AND purpose = ?", (email, purpose)).fetchone()
        if row is None or row["expires_at"] < time.time() or row["attempts"] >= CODE_ATTEMPTS:
            outcome = "expired"
        elif not hmac.compare_digest(row["code_hash"], _sha(f"{purpose}:{email}:{code}")):
            con.execute("UPDATE email_codes SET attempts = attempts + 1 WHERE email = ? AND purpose = ?",
                        (email, purpose))
            outcome = "wrong"
        else:
            con.execute("DELETE FROM email_codes WHERE email = ? AND purpose = ?", (email, purpose))
            outcome = "ok"
    if outcome == "expired":
        raise AuthError("That code has expired. Ask for a new one.")
    if outcome == "wrong":
        raise AuthError("That code isn't right. Check the email and try again.")


# Registration

def start_registration(name: str, email: str, password: str, reason: str = ""):
    """Check the form, remember it, and email a verification code."""
    email = normalize_email(email)
    name, reason = _clean(name, NAME_MAX), _clean(reason, REASON_MAX)
    if not name:
        raise AuthError("Enter your name.")
    if not EMAIL_RE.fullmatch(email):
        raise AuthError("Enter a valid email address.")
    if problem := password_problem(password, email):
        raise AuthError(problem)
    with db.connect() as con:
        if con.execute("SELECT 1 FROM local_accounts WHERE email = ?", (email,)).fetchone():
            raise AuthError("This email already has an account. Sign in, or reset your password.")
    _send_code(email, "register")
    with db.connect() as con:
        con.execute(
            "INSERT INTO pending_registrations (email, name, reason, password_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(email) DO UPDATE SET name = excluded.name, "
            "reason = excluded.reason, password_hash = excluded.password_hash, created_at = excluded.created_at",
            (email, name, reason or None, hash_password(password), time.time()),
        )
    return email


def finish_registration(email: str, code: str) -> str:
    """Verify the code, create the account and its access request, and return a login token."""
    from core import users
    email = normalize_email(email)
    _use_code(email, "register", code)
    with db.connect() as con:
        row = con.execute("SELECT name, reason, password_hash FROM pending_registrations WHERE email = ?",
                          (email,)).fetchone()
        if row is None:
            raise AuthError("Your registration expired. Please register again.")
        con.execute("INSERT OR IGNORE INTO local_accounts (email, name, password_hash, created_at) "
                    "VALUES (?, ?, ?, ?)", (email, row["name"], row["password_hash"], time.time()))
        con.execute("DELETE FROM pending_registrations WHERE email = ?", (email,))
    db.audit("account_created", email=email, detail="email and password")
    # The access request comes with the account, so the admin can approve it
    # straight away. Someone already invited simply gets in.
    try:
        users.authorize(email, True)
    except users.NotInvited:
        try:
            users.request_access(email, name=row["name"], reason=row["reason"])
        except ValueError:
            # Requests are full right now; the account still exists, and the
            # request form appears when they sign in.
            log.warning("access request not recorded for new account %s", email)
    except Exception:
        log.exception("checking access for new account %s failed", email)
    return _new_login_token(email)


# Sign-in

def sign_in(email: str, password: str) -> str:
    """Check a password and return a login token. One message for every failure."""
    email = normalize_email(email)
    wrong = AuthError("Email or password is incorrect.")
    with db.connect() as con:
        row = con.execute("SELECT password_hash, failed_logins, locked_until FROM local_accounts "
                          "WHERE email = ?", (email,)).fetchone()
    if row is None:
        _check_password(password, _DUMMY_HASH)   # same time as a real check
        raise wrong
    if row["locked_until"] > time.time():
        raise AuthError("Too many wrong passwords. Try again in 15 minutes, or reset your password.")
    if not _check_password(password, row["password_hash"]):
        failed = row["failed_logins"] + 1
        locked = time.time() + LOCK_SECONDS if failed >= MAX_FAILED_LOGINS else 0
        with db.connect() as con:
            con.execute("UPDATE local_accounts SET failed_logins = ?, locked_until = ? WHERE email = ?",
                        (0 if locked else failed, locked, email))
        if locked:
            db.audit("account_locked", email=email)
        raise wrong
    with db.connect() as con:
        con.execute("UPDATE local_accounts SET failed_logins = 0, locked_until = 0 WHERE email = ?", (email,))
    return _new_login_token(email)


def start_reset(email: str):
    """Email a reset code if the account exists. Says nothing either way."""
    email = normalize_email(email)
    if not EMAIL_RE.fullmatch(email):
        raise AuthError("Enter a valid email address.")
    with db.connect() as con:
        exists = con.execute("SELECT 1 FROM local_accounts WHERE email = ?", (email,)).fetchone()
    if exists:
        _send_code(email, "reset")
    return email


def finish_reset(email: str, code: str, new_password: str) -> str:
    email = normalize_email(email)
    if problem := password_problem(new_password, email):
        raise AuthError(problem)
    _use_code(email, "reset", code)
    with db.connect() as con:
        con.execute("UPDATE local_accounts SET password_hash = ?, failed_logins = 0, locked_until = 0 "
                    "WHERE email = ?", (hash_password(new_password), email))
        # A new password signs out every other device.
        con.execute("DELETE FROM sessions WHERE email = ?", (email,))
    db.audit("password_reset", email=email)
    return _new_login_token(email)


# Login tokens and sessions

def _new_login_token(email: str) -> str:
    token = secrets.token_urlsafe(32)
    with db.connect() as con:
        con.execute("DELETE FROM login_tokens WHERE expires_at < ?", (time.time(),))
        con.execute("INSERT INTO login_tokens (token_hash, email, expires_at) VALUES (?, ?, ?)",
                    (_sha(token), email, time.time() + LOGIN_TOKEN_SECONDS))
    return token


def redeem_login_token(token: str):
    """Single use: returns (session_token, max_age) or None."""
    with db.connect() as con:
        row = con.execute("SELECT email, expires_at FROM login_tokens WHERE token_hash = ?",
                          (_sha(token or ""),)).fetchone()
        if row is None:
            return None
        con.execute("DELETE FROM login_tokens WHERE token_hash = ?", (_sha(token),))
        if row["expires_at"] < time.time():
            return None
        session = secrets.token_urlsafe(32)
        now = time.time()
        con.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
        con.execute("INSERT INTO sessions (token_hash, email, created_at, expires_at) VALUES (?, ?, ?, ?)",
                    (_sha(session), row["email"], now, now + SESSION_SECONDS))
    db.audit("login", email=row["email"], detail="email and password")
    return session, SESSION_SECONDS


def session_email(session_token: str):
    if not session_token:
        return None
    with db.connect() as con:
        row = con.execute("SELECT email, expires_at FROM sessions WHERE token_hash = ?",
                          (_sha(session_token),)).fetchone()
    if row is None or row["expires_at"] < time.time():
        return None
    return row["email"]


def end_session(session_token: str):
    if session_token:
        with db.connect() as con:
            con.execute("DELETE FROM sessions WHERE token_hash = ?", (_sha(session_token),))


def account_name(email: str):
    with db.connect() as con:
        row = con.execute("SELECT name FROM local_accounts WHERE email = ?", (normalize_email(email),)).fetchone()
    return row["name"] if row else None
