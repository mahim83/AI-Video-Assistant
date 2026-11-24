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


def run(monkeypatch, signed_in_as=None, verified=True, sub=None, secret=STRONG_SECRET,
        session_cookie="", page=None):
    monkeypatch.setattr(core.auth, "_auth_configured", lambda: True)
    monkeypatch.setattr(core.auth, "_cookie_secret", lambda: secret)
    monkeypatch.setattr(core.auth, "_session_cookie", lambda: session_cookie)
    claims = {"email": signed_in_as, "email_verified": verified, "sub": sub} if signed_in_as else {}
    monkeypatch.setattr(streamlit, "user", FakeUser(claims))
    at = AppTest.from_file(APP, default_timeout=300)
    if page:
        at.query_params["page"] = page
    return at.run()


def enable_email(monkeypatch):
    """SMTP configured (so email accounts are offered), with mail captured, not sent."""
    from core import notify
    from core.settings import get_settings
    monkeypatch.setenv("SMTP_USER", "app@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "x" * 16)
    get_settings.cache_clear()
    outbox = []
    monkeypatch.setattr(notify, "send", lambda to, subject, body: outbox.append((to, subject, body)))
    return outbox


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


def invite_only(monkeypatch):
    monkeypatch.setenv("SIGNUP_MODE", "invite")
    from core.settings import get_settings
    get_settings.cache_clear()


def test_denied_logins_are_logged_once_per_hour(monkeypatch):
    invite_only(monkeypatch)
    run(monkeypatch, "stranger@example.com")
    run(monkeypatch, "stranger@example.com")   # a new session, same hour
    assert [r["action"] for r in db.recent_audit()].count("login_denied") == 1


def test_google_sign_up_goes_straight_in(monkeypatch):
    outbox = enable_email(monkeypatch)
    # A new Google account fills in the one-time form...
    at = run(monkeypatch, "newcomer@example.com", sub="google-333")
    assert not at.sidebar.radio
    assert "Finish creating your account." in texts(at)
    at.text_input(key="reg_name").input("New Comer")
    at.button(key="register_submit").click().run()
    assert "Tick the box" in texts(at)                 # consent is required
    assert not users.list_users(users.authorize("owner@example.com", True))[2:]
    at.checkbox(key="reg_agree").check()
    at.text_area(key="reg_reason").input("Summarising my lectures")
    at.button(key="register_submit").click().run()

    # ...and is in at once, as a regular user, with no approval step.
    assert not at.exception
    assert at.sidebar.radio[0].options == ["New video", "Saved meetings"]
    # The admin gets one email about it.
    assert [(to, subject) for to, subject, _ in outbox] == [
        (["owner@example.com"], "New registration: newcomer@example.com")]

    # The admin page has nothing to approve, and the newcomer is listed.
    admin = run(monkeypatch, "owner@example.com")
    admin.sidebar.radio[0].set_value("Admin").run()
    assert not admin.exception
    assert "Approve" not in [b.label for b in admin.button]
    assert "Anyone can sign up" in texts(admin)


def test_revoked_user_sees_no_access(monkeypatch):
    users.register("newcomer@example.com", name="New Comer")
    owner = users.authorize("owner@example.com", True)
    users.remove_user(owner, "newcomer@example.com")
    at = run(monkeypatch, "newcomer@example.com")
    assert "revoked" in texts(at)
    assert "register_submit" not in [b.key for b in at.button]
    assert not at.sidebar.radio


def test_unverified_email_cannot_register(monkeypatch):
    at = run(monkeypatch, "newcomer@example.com", verified=False)
    assert "isn't verified" in texts(at)
    assert "Finish creating your account." not in texts(at)


def test_front_page_has_no_form(monkeypatch):
    at = run(monkeypatch)
    assert not at.exception
    # The front page explains the app; the forms live on their own pages.
    assert not at.button and not at.text_input
    assert "Ask questions about any video" in texts(at)
    # Sign in and Sign up appear once, in the top bar.
    assert texts(at).count('href="?page=signin"') == 1 and texts(at).count('href="?page=register"') == 1
    assert not at.sidebar.radio


def test_sign_in_page_is_only_sign_in(monkeypatch):
    at = run(monkeypatch, page="signin")
    assert not at.exception
    # Without SMTP settings, email accounts aren't offered: Google only.
    assert [b.label for b in at.button] == ["Sign in with Google"]
    assert "Don't have an account?" in texts(at)
    assert "Ask questions about any video" not in texts(at)
    assert "How it works" not in texts(at)


def test_top_bar_links_to_sign_in_and_sign_up(monkeypatch):
    at = run(monkeypatch)
    bar = next(m.value for m in at.markdown if 'class="ava-topbar"' in m.value)
    assert 'href="?page=signin"' in bar and ">Sign in</a>" in bar
    assert 'href="?page=register"' in bar and ">Sign up</a>" in bar

    assert "data-ava-theme" in bar    # the light/dark switch

    # With sign-ups off, the bar offers Sign in only.
    monkeypatch.setenv("SIGNUP_MODE", "invite")
    from core.settings import get_settings
    get_settings.cache_clear()
    at = run(monkeypatch)
    bar = next(m.value for m in at.markdown if 'class="ava-topbar"' in m.value)
    assert ">Sign in</a>" in bar and "Sign up" not in bar


def test_sign_in_page_offers_both_with_email_set_up(monkeypatch):
    enable_email(monkeypatch)
    at = run(monkeypatch, page="signin")
    labels = [b.label for b in at.button]
    assert "Sign in with Google" in labels and "Sign in" in labels
    assert "or sign in with email" in texts(at) and "Forgot your password?" in texts(at)


def test_register_page_with_email(monkeypatch):
    outbox = enable_email(monkeypatch)
    at = run(monkeypatch, page="register")
    assert "Sign up with Google" in [b.label for b in at.button]
    assert "Already registered?" in texts(at)

    at.text_input(key="er_name").input("Asha Rao")
    at.text_input(key="er_email").input("asha@example.com")
    at.text_input(key="er_password").input("river stone lantern")
    at.text_input(key="er_confirm").input("river stone lantern")
    at.checkbox(key="er_agree").check()
    at.button(key="er_submit").click().run()
    assert not at.exception
    assert "Check your email." in texts(at) and "Check your Spam folder." in texts(at)
    code = outbox[-1][1].split()[-1]                 # "Your AI Video Assistant code: 123456"

    at.text_input(key="verify_code").input(code)
    at.button(key="verify_submit").click().run()
    assert "/local-auth/complete?token=" in texts(at)
    assert users.authorize("asha@example.com", True).role == "user"


def test_email_account_session_signs_in(monkeypatch):
    from core import local_auth
    outbox = enable_email(monkeypatch)
    local_auth.start_registration("Asha Rao", "asha@example.com", "river stone lantern")
    code = outbox[-1][1].split()[-1]
    token = local_auth.finish_registration("asha@example.com", code)
    session, _ = local_auth.redeem_login_token(token)

    at = run(monkeypatch, session_cookie=session)
    assert not at.exception
    assert at.sidebar.radio[0].options == ["New video", "Saved meetings"]
    assert "/local-auth/signout" in " ".join(m.value for m in at.sidebar.markdown)


def test_uninvited_account_is_denied_and_audited(monkeypatch):
    invite_only(monkeypatch)
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


def test_upload_only_server_hides_youtube(monkeypatch):
    monkeypatch.setenv("ENABLE_YOUTUBE", "false")
    from core.settings import get_settings
    get_settings.cache_clear()
    at = run(monkeypatch, "friend@example.com")
    assert not at.exception
    assert not at.sidebar.text_input            # no YouTube URL box
    assert "save its audio as a file" in " ".join(c.value for c in at.sidebar.caption)


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
