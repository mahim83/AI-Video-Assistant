"""
Sign-in for the web app, two ways:

- Google, through Streamlit's built-in OIDC support (st.login, configured in
  .streamlit/secrets.toml);
- email and password (core/local_auth.py), whose session lives in an
  HttpOnly cookie set by server.py.

Either way the identity is checked against the user list on every rerun, so
access revoked by an admin applies at the user's next click.
"""
import time

import streamlit as st

from core import db, local_auth, ui, users
from core.errors import AccessDenied
from core.settings import get_settings
from core.users import LOCAL_USER, NotInvited, User, authorize

SIGN_OUT_LOCAL = "/local-auth/signout"

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


def _session_cookie() -> str:
    """The email-account session cookie, read from the connection's own request."""
    try:
        return st.context.cookies.get(local_auth.SESSION_COOKIE, "") or ""
    except Exception:
        return ""


def signed_in_with_password() -> bool:
    return st.session_state.get("_auth_method") == "password"


def sign_out_href():
    """Where "Sign out" goes: email accounts clear their cookie at this route."""
    return SIGN_OUT_LOCAL if signed_in_with_password() else None


def _deny(email, message: str):
    label = str(email or "?")
    # At most one row per email per hour, so scripted sign-ins can't push
    # real events out of the admin's view.
    if st.session_state.get("_denied_email") != email:
        st.session_state["_denied_email"] = email
        if not db.audited_since("login_denied", label, time.time() - 3600):
            db.audit("login_denied", email=label)
    ui.denied_page(message, signout_href=sign_out_href())
    st.stop()


def _register(email: str, sub, name: str = None, reason: str = None, method: str = "Google"):
    try:
        return users.register(email, sub, name=name, reason=reason, method=method)
    except AccessDenied as e:
        _deny(email, str(e))


def _signed_out_pages():
    page = st.query_params.get("page")
    if page == "signin":
        ui.sign_in_page()
    elif page == "register":
        ui.register_page()
    elif page == "reset":
        ui.reset_page()
    else:
        ui.home_page()
    st.stop()


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

    if st.user.is_logged_in:
        st.session_state["_auth_method"] = "google"
        email, verified, sub = st.user.get("email"), st.user.get("email_verified"), st.user.get("sub")
        default_name = st.user.get("name") or ""
    elif (email := local_auth.session_email(_session_cookie())):
        # Email accounts are verified with a code before they exist.
        st.session_state["_auth_method"] = "password"
        verified, sub = True, None
        default_name = local_auth.account_name(email) or ""
    else:
        st.session_state.pop("_auth_method", None)
        _signed_out_pages()

    try:
        user = authorize(email, verified, sub)
    except NotInvited as e:
        if settings.signup_mode != "open":
            _deny(email, str(e))
        if signed_in_with_password():
            # Email accounts agreed to how recordings are processed when they
            # signed up; this catches accounts made before sign-up was open.
            user = _register(e.email, sub, name=default_name, method="email")
        else:
            # First Google sign-in: one short form, then straight in.
            form = ui.register_google_page(e.email, default_name=default_name,
                                           signout_href=sign_out_href())
            if form is None:
                st.stop()
            _register(e.email, sub, name=form[0], reason=form[1])
            st.rerun()
    except AccessDenied as e:
        _deny(email, str(e))

    if st.session_state.get("_signed_in_as") != user.id:
        st.session_state["_signed_in_as"] = user.id
        db.audit("login", user)
        if default_name:
            # So the admin sees names for people who signed up before names were kept.
            users.remember_name(user.email, default_name)
    return user
