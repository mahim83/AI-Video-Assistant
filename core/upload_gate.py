"""
Gate for Streamlit's file-upload endpoint.

Streamlit accepts PUT /_stcore/upload_file/... from any page session, signed
in or not, and keeps each file in memory until the session ends. Without this
gate, an anonymous visitor could upload 200 MB files in a loop and run the
server out of memory.

This ASGI middleware lets an upload through only when the request carries a
valid Streamlit login cookie for an invited user, and limits each user to one
upload at a time and a few per window. It runs in front of Streamlit, so a
refused upload never reaches memory.
"""
import json
import logging
import threading
import time
from collections import defaultdict, deque
from http.cookies import CookieError, SimpleCookie
from urllib.parse import urlsplit

from core.errors import AccessDenied
from core.settings import get_settings
from core.users import authorize

log = logging.getLogger(__name__)

UPLOAD_PATH = "/_stcore/upload_file"
UPLOADS_PER_WINDOW = 4
WINDOW_SECONDS = 600
MAX_IN_FLIGHT_TOTAL = 3

_lock = threading.Lock()
_in_flight = defaultdict(int)       # user id -> uploads currently streaming
_recent = defaultdict(deque)        # user id -> start times within the window


def _app_origin() -> str:
    """scheme://host of the redirect_uri in secrets.toml: where cookies are issued."""
    from streamlit.runtime.secrets import secrets_singleton
    redirect = urlsplit(secrets_singleton["auth"]["redirect_uri"])
    return f"{redirect.scheme}://{redirect.netloc}"


def _user_from_cookie(headers: dict):
    """The invited user behind a request's login cookie (Google or email account), or None."""
    from streamlit.web.server import server_util
    from streamlit.web.server.starlette.starlette_app_utils import decode_signed_value
    from streamlit.web.server.starlette.starlette_server_config import USER_COOKIE_NAME

    from core import local_auth

    try:
        cookies = SimpleCookie(headers.get("cookie", ""))
    except CookieError:
        return None

    # Email and password accounts: a session looked up server-side.
    session = cookies.get(local_auth.SESSION_COOKIE)
    if session is not None and (email := local_auth.session_email(session.value)):
        try:
            return authorize(email, True)
        except AccessDenied:
            return None

    morsel = cookies.get(USER_COOKIE_NAME)
    if morsel is None:
        return None

    # Same steps Streamlit takes for the WebSocket: verify the signature, then
    # check the cookie was issued for this app's origin.
    decoded = decode_signed_value(server_util.get_cookie_secret(), USER_COOKIE_NAME,
                                  morsel.value.encode("latin-1"))
    if decoded is None:
        return None
    try:
        payload = json.loads(decoded.decode("utf-8"))
        origin = _app_origin()
    except Exception:
        return None
    if payload.get("origin") != origin or not payload.get("is_logged_in"):
        return None
    try:
        return authorize(payload.get("email"), payload.get("email_verified"), payload.get("sub"))
    except AccessDenied:
        return None


async def _refuse(send, status: int, message: str):
    body = message.encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"text/plain; charset=utf-8"),
                            (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})


class UploadGate:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if not (scope["type"] == "http" and scope["method"] == "PUT"
                and scope["path"].startswith(UPLOAD_PATH)):
            await self.app(scope, receive, send)
            return
        # Local use without sign-in: the app itself refuses to run that way
        # unless it listens on localhost only.
        if get_settings().auth_mode == "off":
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        user = _user_from_cookie(headers)
        if user is None:
            log.warning("upload refused: no valid sign-in")
            await _refuse(send, 403, "Sign in to upload files.")
            return

        now = time.time()
        with _lock:
            recent = _recent[user.id]
            while recent and recent[0] < now - WINDOW_SECONDS:
                recent.popleft()
            if _in_flight[user.id] >= 1:
                refusal = (429, "Wait for your current upload to finish.")
            elif sum(_in_flight.values()) >= MAX_IN_FLIGHT_TOTAL:
                refusal = (429, "The server is busy with other uploads. Try again shortly.")
            elif len(recent) >= UPLOADS_PER_WINDOW:
                refusal = (429, "Too many uploads. Wait a few minutes and try again.")
            else:
                refusal = None
                _in_flight[user.id] += 1
                recent.append(now)
        if refusal:
            log.warning("upload refused for user=%s: %s", user.id, refusal[1])
            await _refuse(send, *refusal)
            return

        try:
            await self.app(scope, receive, send)
        finally:
            with _lock:
                _in_flight[user.id] -= 1
