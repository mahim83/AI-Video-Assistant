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
    assert "approved" in body and "https://video.example.com" in body


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
