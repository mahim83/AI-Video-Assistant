"""Email + password accounts: registration, sign-in, lockout, reset, sessions."""
import time

import pytest

from core import db, local_auth, notify, users
from core.local_auth import AuthError
from core.settings import get_settings

PASSWORD = "river stone lantern"


@pytest.fixture
def outbox(monkeypatch):
    monkeypatch.setenv("SMTP_USER", "app@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "x" * 16)
    get_settings.cache_clear()
    sent = []
    monkeypatch.setattr(notify, "send", lambda to, subject, body: sent.append((to, subject, body)))
    return sent


def last_code(outbox) -> str:
    return outbox[-1][1].split()[-1]


def register(outbox, email="asha@example.com", password=PASSWORD):
    local_auth.start_registration("Asha Rao", email, password, "lectures")
    return local_auth.finish_registration(email, last_code(outbox))


def test_passwords_are_hashed_not_stored(outbox):
    register(outbox)
    with db.connect() as con:
        stored = con.execute("SELECT password_hash FROM local_accounts").fetchone()[0]
    assert PASSWORD not in stored and stored.startswith("scrypt$")


@pytest.mark.parametrize("password", ["short", "password123", "aaaaaaaaaaaa", "asha-secret-99"])
def test_weak_passwords_rejected(outbox, password):
    with pytest.raises(AuthError):
        local_auth.start_registration("Asha", "asha@example.com", password)


def test_registration_needs_the_emailed_code(outbox):
    local_auth.start_registration("Asha Rao", "asha@example.com", PASSWORD, "lectures")
    assert outbox[-1][0] == "asha@example.com"
    with pytest.raises(AuthError, match="isn't right"):
        local_auth.finish_registration("asha@example.com", "000000" if last_code(outbox) != "000000" else "111111")
    token = local_auth.finish_registration("asha@example.com", last_code(outbox))
    assert token
    # The account can be used at once, and the admin is told, name and reason included.
    assert users.authorize("asha@example.com", True).role == "user"
    to, subject, body = outbox[-1]
    assert to == ["owner@example.com"] and "asha@example.com" in subject
    assert "Asha Rao" in body and "lectures" in body


def test_revoked_email_gets_an_account_but_no_access(outbox):
    owner = users.authorize("owner@example.com", True)
    users.register("asha@example.com")
    users.remove_user(owner, "asha@example.com")
    assert register(outbox)                     # the account is made...
    with pytest.raises(users.AccessDenied, match="revoked"):
        users.authorize("asha@example.com", True)   # ...but it can't get in


def test_code_stops_working_after_five_wrong_tries(outbox):
    local_auth.start_registration("Asha Rao", "asha@example.com", PASSWORD)
    good = last_code(outbox)
    bad = "000000" if good != "000000" else "111111"
    for _ in range(5):
        with pytest.raises(AuthError):
            local_auth.finish_registration("asha@example.com", bad)
    with pytest.raises(AuthError, match="expired"):
        local_auth.finish_registration("asha@example.com", good)


def test_no_email_accounts_without_smtp():
    with pytest.raises(AuthError, match="Use Google"):
        local_auth.start_registration("Asha", "asha@example.com", PASSWORD)


def test_cannot_register_an_email_twice(outbox):
    register(outbox)
    with pytest.raises(AuthError, match="already has an account"):
        local_auth.start_registration("Someone", "asha@example.com", PASSWORD)


def test_code_resend_is_rate_limited(outbox):
    local_auth.start_registration("Asha Rao", "asha@example.com", PASSWORD)
    with pytest.raises(AuthError, match="Wait a minute"):
        local_auth._send_code("asha@example.com", "register")


def test_sign_in_and_one_message_for_every_failure(outbox):
    register(outbox)
    assert local_auth.sign_in("ASHA@example.com", PASSWORD)
    with pytest.raises(AuthError) as wrong_password:
        local_auth.sign_in("asha@example.com", "not the password")
    with pytest.raises(AuthError) as no_account:
        local_auth.sign_in("nobody@example.com", PASSWORD)
    assert str(wrong_password.value) == str(no_account.value) == "Email or password is incorrect."


def test_five_wrong_passwords_lock_the_account(outbox):
    register(outbox)
    for _ in range(5):
        with pytest.raises(AuthError):
            local_auth.sign_in("asha@example.com", "wrong password here")
    with pytest.raises(AuthError, match="15 minutes"):
        local_auth.sign_in("asha@example.com", PASSWORD)   # even the right one, for now


def test_login_token_is_single_use_and_short_lived(outbox, monkeypatch):
    token = register(outbox)
    session, max_age = local_auth.redeem_login_token(token)
    assert local_auth.session_email(session) == "asha@example.com"
    assert local_auth.redeem_login_token(token) is None            # used up

    later = local_auth.sign_in("asha@example.com", PASSWORD)
    real_time = time.time
    monkeypatch.setattr(local_auth.time, "time", lambda: real_time() + 600)
    assert local_auth.redeem_login_token(later) is None            # expired


def test_sign_out_ends_the_session(outbox):
    session, _ = local_auth.redeem_login_token(register(outbox))
    local_auth.end_session(session)
    assert local_auth.session_email(session) is None


def test_reset_password(outbox):
    session, _ = local_auth.redeem_login_token(register(outbox))
    sent_before = len(outbox)
    local_auth.start_reset("nobody@example.com")                     # no account: nothing sent, no error
    assert len(outbox) == sent_before
    local_auth.start_reset("asha@example.com")
    token = local_auth.finish_reset("asha@example.com", last_code(outbox), "new harbour morning")
    assert token
    assert local_auth.session_email(session) is None                  # other devices signed out
    with pytest.raises(AuthError):
        local_auth.sign_in("asha@example.com", PASSWORD)
    assert local_auth.sign_in("asha@example.com", "new harbour morning")


def test_upload_gate_follows_access(outbox, monkeypatch):
    import asyncio
    from core import upload_gate

    owner = users.authorize("owner@example.com", True)
    session, _ = local_auth.redeem_login_token(register(outbox))

    def put():
        sent = []
        scope = {"type": "http", "method": "PUT", "path": "/_stcore/upload_file/s/f",
                 "headers": [(b"cookie", f"{local_auth.SESSION_COOKIE}={session}".encode())]}

        async def inner(scope, receive, send):
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        async def send(m):
            sent.append(m)
        asyncio.run(upload_gate.UploadGate(inner)(scope, None, send))
        return sent[0]["status"]

    upload_gate._in_flight.clear(); upload_gate._recent.clear()
    assert put() == 204                      # usable as soon as it's registered
    users.remove_user(owner, "asha@example.com")
    upload_gate._in_flight.clear(); upload_gate._recent.clear()
    assert put() == 403                      # revoked
