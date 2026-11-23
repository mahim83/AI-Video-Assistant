"""
The sign-in flow, end to end through Streamlit's AppTest. AppTest can't sign
in, so st.user is replaced by a stand-in for what Google returns.
"""
import os

import pytest
import streamlit
from streamlit import config as st_config
from streamlit.testing.v1 import AppTest

import core.auth
from core import db, storage, users

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")


class FakeUser(dict):
    @property
    def is_logged_in(self):
        return bool(self)


STRONG_SECRET = "s" * 48


def run(monkeypatch, signed_in_as=None, verified=True, sub=None, secret=STRONG_SECRET):
    monkeypatch.setattr(core.auth, "_auth_configured", lambda: True)
    monkeypatch.setattr(core.auth, "_cookie_secret", lambda: secret)
    claims = {"email": signed_in_as, "email_verified": verified, "sub": sub} if signed_in_as else {}
    monkeypatch.setattr(streamlit, "user", FakeUser(claims))
    return AppTest.from_file(APP, default_timeout=300).run()


def texts(at):
    return " ".join(e.value for e in list(at.markdown) + list(at.error) + list(at.caption))


@pytest.mark.parametrize("secret", ["replace-with-a-long-random-string", "short", ""])
def test_weak_cookie_secret_stops_the_app(monkeypatch, secret):
    at = run(monkeypatch, "owner@example.com", secret=secret)
    assert "cookie_secret" in texts(at)
    assert not at.sidebar.radio and not at.button


def test_email_bound_to_first_google_account(monkeypatch):
    assert run(monkeypatch, "friend@example.com", sub="google-111").sidebar.radio
    at = run(monkeypatch, "friend@example.com", sub="google-222")
    assert "different Google account" in texts(at)
    assert not at.sidebar.radio


def test_denied_logins_are_logged_once_per_hour(monkeypatch):
    run(monkeypatch, "stranger@example.com")
    run(monkeypatch, "stranger@example.com")   # a new session, same hour
    assert [r["action"] for r in db.recent_audit()].count("login_denied") == 1


def test_signed_out_sees_only_sign_in(monkeypatch):
    at = run(monkeypatch)
    assert not at.exception
    assert [b.label for b in at.button] == ["Continue with Google"]
    assert not at.sidebar.radio


def test_uninvited_account_is_denied_and_audited(monkeypatch):
    at = run(monkeypatch, "stranger@example.com")
    assert not at.exception
    assert "isn't on this app's invite list" in texts(at)
    assert not at.sidebar.radio
    assert db.recent_audit()[0]["action"] == "login_denied"


def test_unverified_email_is_denied(monkeypatch):
    at = run(monkeypatch, "friend@example.com", verified=False)
    assert "isn't verified" in texts(at)
    assert not at.sidebar.radio


def test_invited_user_has_no_admin_and_sees_own_meetings_only(monkeypatch):
    other = storage.user_space(users.user_id_for("owner@example.com"))
    storage.save_meeting(other, {"title": "t", "transcript": "x", "summary": "s",
                                 "collection_name": "owners_meeting_20260101_000000"}, "src")

    at = run(monkeypatch, "friend@example.com")
    assert not at.exception
    assert at.sidebar.radio[0].options == ["New video", "Saved meetings"]
    at.sidebar.radio[0].set_value("Saved meetings").run()
    assert "No saved meetings yet" in " ".join(i.value for i in at.sidebar.info)


def test_admin_page(monkeypatch):
    at = run(monkeypatch, "owner@example.com")
    assert "Admin" in at.sidebar.radio[0].options
    at.sidebar.radio[0].set_value("Admin").run()
    assert not at.exception
    emails = list(at.dataframe[0].value["Email"])
    assert emails == ["owner@example.com", "friend@example.com"]


def test_auth_off_refused_on_a_network_address(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "off")
    from core.settings import get_settings
    get_settings.cache_clear()
    previous = st_config.get_option("server.address")
    st_config.set_option("server.address", "0.0.0.0")
    try:
        at = AppTest.from_file(APP, default_timeout=300).run()
    finally:
        st_config.set_option("server.address", previous)
    assert "allowed only while the app listens on localhost" in texts(at)
    assert not at.sidebar.radio
