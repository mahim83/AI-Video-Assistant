import pytest

from core import notify, users
from core.settings import get_settings


@pytest.fixture
def outbox(monkeypatch):
    """Capture emails instead of sending them, synchronously."""
    sent = []
    monkeypatch.setattr(notify, "_send", lambda to, subject, body: sent.append((to, subject, body)))

    class Now:
        def __init__(self, target, args, daemon):
            self.target, self.args = target, args

        def start(self):
            self.target(*self.args)

    monkeypatch.setattr(notify.threading, "Thread", Now)
    return sent


def configure(monkeypatch):
    monkeypatch.setenv("SMTP_USER", "app@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "abcd efgh ijkl mnop")
    monkeypatch.setenv("DOMAIN", "video.example.com")
    get_settings.cache_clear()


def test_nothing_sent_without_smtp(outbox):
    users.request_access("newcomer@example.com")
    assert outbox == [] and not notify.enabled()


def test_admin_hears_about_requests_and_user_about_approval(monkeypatch, outbox, owner):
    configure(monkeypatch)
    assert get_settings().smtp_password == "abcdefghijklmnop"   # spaces removed

    users.request_access("newcomer@example.com")
    to, subject, body = outbox[-1]
    assert to == ["owner@example.com"]
    assert "newcomer@example.com" in subject
    assert "https://video.example.com" in body

    users.approve_request(owner, "newcomer@example.com")
    to, subject, body = outbox[-1]
    assert to == ["newcomer@example.com"]
    assert subject == "You can now use AI Video Assistant"
    assert "approved" in body and "https://video.example.com/?page=signin" in body
    assert "Sign in with Google" in body     # no password account: told to use Google


def test_approval_email_greets_by_name_and_says_how_to_sign_in(monkeypatch, outbox, owner):
    configure(monkeypatch)
    from core import db, local_auth
    with db.connect() as con:
        con.execute("INSERT INTO local_accounts (email, name, password_hash, created_at) VALUES (?, ?, ?, 0)",
                    ("asha@example.com", "Asha Rao", local_auth.hash_password("river stone lantern")))
    users.request_access("asha@example.com", name="Asha Rao")
    users.approve_request(owner, "asha@example.com")
    to, subject, body = outbox[-1]
    assert to == ["asha@example.com"]
    assert body.startswith("Hi Asha Rao,")
    assert "email and password you registered with" in body and "Google" not in body


def test_invite_emails_only_new_users(monkeypatch, outbox, owner):
    configure(monkeypatch)
    assert users.add_user(owner, "friend@example.com", "user", send_invite=True) is True
    to, subject, body = outbox[-1]
    assert to == ["friend@example.com"] and subject == "You're invited to AI Video Assistant"
    assert "https://video.example.com/?page=signin" in body

    sent = len(outbox)
    users.add_user(owner, "friend@example.com", "admin", send_invite=True)   # a role change
    assert len(outbox) == sent
    users.add_user(owner, "quiet@example.com", "user")                       # no invite asked for
    assert len(outbox) == sent


def test_repeat_request_sends_no_second_email(monkeypatch, outbox):
    configure(monkeypatch)
    users.request_access("newcomer@example.com")
    users.request_access("newcomer@example.com")
    assert len(outbox) == 1


def test_header_injection_is_refused(monkeypatch):
    configure(monkeypatch)
    # The real _send builds the message: a newline in a header is rejected
    # before anything is sent, and the error is logged, not raised.
    called = []
    monkeypatch.setattr(notify.smtplib, "SMTP_SSL", lambda *a, **k: called.append(1))
    notify._send(["x@example.com"], "hi\r\nBcc: victim@example.com", "body")
    assert called == []


def test_codes_never_reach_the_log(monkeypatch, caplog):
    configure(monkeypatch)

    class FakeSMTP:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def ehlo(self): pass
        def auth(self, *a): pass
        def auth_plain(self): return ""
        def send_message(self, msg): pass

    monkeypatch.setattr(notify.smtplib, "SMTP_SSL", FakeSMTP)
    with caplog.at_level("INFO", logger="core.notify"):
        notify._send(["x@example.com"], "Your AI Video Assistant code: 328160", "Your code is 328160.")
    assert "email sent" in caplog.text and "328160" not in caplog.text
