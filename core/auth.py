"""
Sign-in for the web app. Google login runs through Streamlit's built-in OIDC
support (st.login, configured in .streamlit/secrets.toml). The identity it
returns is checked against the invite list on every rerun, so access granted
or revoked by an admin applies at the user's next click.
"""
import streamlit as st

from core import db, ui
from core.errors import AccessDenied
from core.settings import get_settings
from core.users import LOCAL_USER, User, authorize

LOOPBACK = ("localhost", "127.0.0.1", "::1")


def _auth_configured() -> bool:
    try:
        return "auth" in st.secrets
    except Exception:   # no secrets.toml at all
        return False


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

    if not st.user.is_logged_in:
        ui.sign_in_page()
        st.stop()

    email = st.user.get("email")
    try:
        user = authorize(email, st.user.get("email_verified"))
    except AccessDenied as e:
        if st.session_state.get("_denied_email") != email:
            st.session_state["_denied_email"] = email
            db.audit("login_denied", email=str(email or "?"))
        ui.denied_page(str(e))
        st.stop()

    if st.session_state.get("_signed_in_as") != user.id:
        st.session_state["_signed_in_as"] = user.id
        db.audit("login", user)
    return user
