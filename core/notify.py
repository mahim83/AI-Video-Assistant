"""
Email notifications through an SMTP account (Gmail with an app password by
default): admins hear about each new registration, and people an admin
invites hear how to sign in. Sign-up and password-reset codes go out the
same way (core/local_auth.py).

Sending happens on a background thread so a slow or failing mail server
never holds up the page, and a failure is logged rather than shown. With no
SMTP_USER/SMTP_PASSWORD set, nothing is sent.
"""
import logging
import re
import smtplib
import ssl
import threading
from email.message import EmailMessage

from core.settings import get_settings

log = logging.getLogger(__name__)


def enabled() -> bool:
    s = get_settings()
    return bool(s.smtp_user and s.smtp_password)


_DIGITS = re.compile(r"\d{4,}")


def _for_log(subject: str) -> str:
    """The subject without sign-in codes, so the server log never holds one."""
    return _DIGITS.sub("[code]", subject)


def _send(to: list, subject: str, body: str):
    s = get_settings()
    try:
        msg = EmailMessage()   # refuses CR/LF in headers, so no header injection
        msg["From"] = f"AI Video Assistant <{s.smtp_user}>"
        msg["To"] = ", ".join(to)
        msg["Subject"] = subject
        msg.set_content(body)
        with smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=20,
                              context=ssl.create_default_context()) as smtp:
            smtp.ehlo()
            # One method only: login() would try another after a rejection,
            # Gmail then hangs up, and the real "535 bad credentials" turns
            # into a misleading "connection unexpectedly closed".
            smtp.user, smtp.password = s.smtp_user, s.smtp_password
            smtp.auth("PLAIN", smtp.auth_plain)
            smtp.send_message(msg)
        log.info("email sent: %s", _for_log(subject))
    except smtplib.SMTPAuthenticationError as e:
        log.error("email failed: the mail server rejected SMTP_USER/SMTP_PASSWORD (%s). "
                  "With Gmail, use an app password of that same account.", e.smtp_code)
    except Exception:
        log.exception("email failed: %s", _for_log(subject))


def send(to, subject: str, body: str):
    recipients = [t for t in ([to] if isinstance(to, str) else to) if t]
    if not enabled() or not recipients:
        return
    threading.Thread(target=_send, args=(recipients, subject, body), daemon=True).start()


def new_registration(email: str, name: str = None, reason: str = None, method: str = "Google"):
    """To the admins: someone registered and can already use the app."""
    s = get_settings()
    who = f"{name} ({email})" if name else email
    how = "their Google account" if method == "Google" else "an email and password"
    lines = [f"{who} registered for AI Video Assistant with {how} and can use it now."]
    if reason:
        lines.append(f"How they'll use it: {reason}")
    lines.append(f"If it looks suspicious, revoke their access on the Admin page: {s.app_url}")
    send(sorted(s.notify_emails), f"New registration: {email}", "\n\n".join(lines) + "\n")


_WHAT_IT_DOES = ("Upload a recording of a meeting, lecture or video, and you get the full transcript, "
                 "a short summary, and answers to your questions about it.")


def _how_to_sign_in(email: str, has_password: bool) -> str:
    if has_password:
        return f"Sign in with the email and password you registered with ({email})."
    return (f'Choose "Sign in with Google" and use this Google account: {email}. '
            "Or create a password for this address on the Sign up page.")


def invited(email: str, role: str):
    """To someone the admin added directly from the Admin page."""
    s = get_settings()
    as_admin = " as an admin" if role == "admin" else ""
    send(
        email,
        "You're invited to AI Video Assistant",
        "Hi,\n\n"
        f"You've been given access to AI Video Assistant{as_admin}, so you can start using it now.\n\n"
        f"Sign in here: {s.app_url}/?page=signin\n"
        f"{_how_to_sign_in(email, False)}\n\n"
        f"{_WHAT_IT_DOES}\n\n"
        "If you weren't expecting this, you can ignore this email.\n",
    )
