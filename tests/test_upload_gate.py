"""
The upload gate, with real login cookies signed the way Streamlit signs them.
"""
import asyncio
import json

import pytest
from streamlit.web.server import server_util
from streamlit.web.server.starlette.starlette_app_utils import create_signed_value

from core import upload_gate

SECRET = "x" * 48
ORIGIN = "https://video.example.com"
UPLOAD = "/_stcore/upload_file/session-1/file-1"


@pytest.fixture(autouse=True)
def gate_env(monkeypatch):
    monkeypatch.setattr(server_util, "get_cookie_secret", lambda: SECRET)
    monkeypatch.setattr(upload_gate, "_app_origin", lambda: ORIGIN)
    upload_gate._in_flight.clear()
    upload_gate._recent.clear()


def cookie(email="friend@example.com", secret=SECRET, origin=ORIGIN, verified=True):
    payload = json.dumps({"email": email, "email_verified": verified,
                          "is_logged_in": True, "origin": origin})
    return "_streamlit_user=" + create_signed_value(secret, "_streamlit_user", payload).decode()


class Inner:
    """Stands in for Streamlit; records whether the request got through."""
    def __init__(self, hold=None):
        self.calls = 0
        self.hold = hold

    async def __call__(self, scope, receive, send):
        self.calls += 1
        if self.hold:
            await self.hold.wait()
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})


def request(gate, path=UPLOAD, method="PUT", cookie_header=None):
    headers = [(b"cookie", cookie_header.encode())] if cookie_header else []
    scope = {"type": "http", "method": method, "path": path, "headers": headers}
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    asyncio.run(gate(scope, receive, send))
    return sent[0]["status"]


@pytest.mark.parametrize("cookie_header", [
    None,                                         # anonymous visitor
    cookie(secret="y" * 48),                      # forged signature
    cookie(origin="https://evil.example"),        # issued for another site
    cookie(email="stranger@example.com"),         # signed in, not invited
    cookie(verified=False),                       # unverified email
    "_streamlit_user=not-a-signed-value",
])
def test_refused_without_valid_invited_sign_in(cookie_header):
    inner = Inner()
    assert request(upload_gate.UploadGate(inner), cookie_header=cookie_header) == 403
    assert inner.calls == 0


def test_invited_user_can_upload():
    inner = Inner()
    assert request(upload_gate.UploadGate(inner), cookie_header=cookie()) == 204
    assert inner.calls == 1


def test_other_requests_are_untouched():
    inner = Inner()
    gate = upload_gate.UploadGate(inner)
    assert request(gate, path="/") == 204
    assert request(gate, method="DELETE") == 204   # removing an upload frees memory


def test_upload_rate_limit():
    gate = upload_gate.UploadGate(Inner())
    for _ in range(upload_gate.UPLOADS_PER_WINDOW):
        assert request(gate, cookie_header=cookie()) == 204
    assert request(gate, cookie_header=cookie()) == 429


def test_one_upload_at_a_time_per_user():
    async def scenario():
        hold = asyncio.Event()
        gate = upload_gate.UploadGate(Inner(hold))
        statuses = []

        async def put():
            sent = []
            scope = {"type": "http", "method": "PUT", "path": UPLOAD,
                     "headers": [(b"cookie", cookie().encode())]}

            async def send(m):
                sent.append(m)
            await gate(scope, None, send)
            statuses.append(sent[0]["status"])

        first = asyncio.create_task(put())
        await asyncio.sleep(0)                 # first upload is now streaming
        await put()                            # second one is refused
        hold.set()
        await first
        return statuses

    assert asyncio.run(scenario()) == [429, 204]


def test_auth_off_lets_uploads_through(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "off")
    from core.settings import get_settings
    get_settings.cache_clear()
    assert request(upload_gate.UploadGate(Inner())) == 204
