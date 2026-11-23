"""
Sign-in for the web app. Google login runs through Streamlit's built-in OIDC
support (st.login, configured in .streamlit/secrets.toml). The identity it
returns is checked against the invite list on every rerun, so access granted
or revoked by an admin applies at the user's next click.
"""
import time

import streamlit as st

from core import db, ui, users
from core.errors import AccessDenied
from core.settings import get_settings
from core.users import LOCAL_USER, NotInvited, User, authorize

LOOPBACK = ("localhost", "127.0.0.1", "::1")
# The placeholder in .streamlit/secrets.toml.example.
EXAMPLE_COOKIE_SECRET = "replace-with-a-long-random-string"
MIN_COOKIE_SECRET_CHARS = 32


def _auth_configured() -> bool:
    try:
        return "auth" in st.secrets
    except Exception:   # no secrets.toml at all
        return False


def _cookie_secret() -> str:
    return str(st.secrets["auth"].get("cookie_secret", ""))


def cookie_secret_problem(secret: str):
    """
    The login cookie is signed with cookie_secret. Anyone who knows or guesses
    it can forge a cookie for any email, including an admin's, so a weak one
    must stop the app instead of only logging a warning.
    """
    if secret == EXAMPLE_COOKIE_SECRET or len(secret) < MIN_COOKIE_SECRET_CHARS:
        return (
            "cookie_secret in .streamlit/secrets.toml is missing, the example value, or shorter "
            f"than {MIN_COOKIE_SECRET_CHARS} characters. Generate one with "
            "python3 -c \"import secrets; print(secrets.token_urlsafe(48))\" and restart the app."
        )
    return None


def _deny(email, message: str):
    label = str(email or "?")
    # At most one row per email per hour, so scripted sign-ins can't push
    # real events out of the admin's view.
    if st.session_state.get("_denied_email") != email:
        st.session_state["_denied_email"] = email
        if not db.audited_since("login_denied", label, time.time() - 3600):
            db.audit("login_denied", email=label)
    ui.denied_page(message)
    st.stop()


def _submit_request(email: str, sub):
    try:
        users.request_access(email, sub)
    except ValueError as e:
        st.session_state["_request_error"] = str(e)


def require_user() -> User:
    """
    Return the signed-in, invited user. Otherwise render the sign-in or
    access-denied page and stop the script, so nothing below the call runs.
    """
    settings = get_settings()

    if settings.auth_mode == "off":
        # Without this check, AUTH_MODE=off on a server would hand everyone admin.
        if st.get_option("server.address") not in LOOPBACK:
            st.error(
                "Sign-in is off (AUTH_MODE=off), which is allowed only while the app listens "
                "on localhost. Set AUTH_MODE=oidc and configure Google sign-in to serve it "
                "on a network."
            )
            st.stop()
        return LOCAL_USER

    if not _auth_configured():
        st.error(
            "Google sign-in isn't configured. Add an [auth] section to .streamlit/secrets.toml "
            "(see DEPLOY.md), or set AUTH_MODE=off in .env to use the app on this computer only."
        )
        st.stop()

    if problem := cookie_secret_problem(_cookie_secret()):
        st.error(problem)
        st.stop()

    if not st.user.is_logged_in:
        ui.sign_in_page()
        st.stop()

    email = st.user.get("email")
    sub = st.user.get("sub")
    try:
        user = authorize(email, st.user.get("email_verified"), sub)
    except NotInvited as e:
        if settings.signup_mode != "request":
            _deny(email, str(e))
        status = users.request_status(e.email)
        if status == "rejected":
            _deny(email, "Your request to use this app was declined.")
        ui.request_page(e.email, status, on_request=_submit_request, on_request_args=(e.email, sub),
                        error=st.session_state.pop("_request_error", None))
        st.stop()
    except AccessDenied as e:
        _deny(email, str(e))

    if st.session_state.get("_signed_in_as") != user.id:
        st.session_state["_signed_in_as"] = user.id
        db.audit("login", user)
    return user
