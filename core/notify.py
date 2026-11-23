"""
Email notifications through an SMTP account (Gmail with an app password by
default): admins hear about new access requests, and people hear when
they've been approved.

Sending happens on a background thread so a slow or failing mail server
never holds up the page, and a failure is logged rather than shown. With no
SMTP_USER/SMTP_PASSWORD set, nothing is sent.
"""
import logging
import smtplib
import ssl
import threading
from email.message import EmailMessage

from core.settings import get_settings

log = logging.getLogger(__name__)


def enabled() -> bool:
    s = get_settings()
    return bool(s.smtp_user and s.smtp_password)


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
        log.info("email sent: %s", subject)
    except smtplib.SMTPAuthenticationError as e:
        log.error("email failed: the mail server rejected SMTP_USER/SMTP_PASSWORD (%s). "
                  "With Gmail, use an app password of that same account.", e.smtp_code)
    except Exception:
        log.exception("email failed: %s", subject)


def send(to, subject: str, body: str):
    recipients = [t for t in ([to] if isinstance(to, str) else to) if t]
    if not enabled() or not recipients:
        return
    threading.Thread(target=_send, args=(recipients, subject, body), daemon=True).start()


def new_access_request(email: str, name: str = None, reason: str = None):
    s = get_settings()
    who = f"{name} ({email})" if name else email
    lines = [f"{who} registered for AI Video Assistant with their Google account."]
    if reason:
        lines.append(f"How they'll use it: {reason}")
    lines.append(f"Approve or reject it on the Admin page: {s.app_url}")
    send(sorted(s.notify_emails), f"New registration: {email}", "\n\n".join(lines) + "\n")


def access_approved(email: str):
    s = get_settings()
    send(
        email,
        "You can now use AI Video Assistant",
        "Your request to use AI Video Assistant was approved.\n\n"
        f"Sign in with this Google account: {s.app_url}\n",
    )
