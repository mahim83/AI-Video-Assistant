"""
Production entry point: the same app as app.py, with two additions in front
of Streamlit. Start it the usual way:

    streamlit run server.py

- The upload gate (core/upload_gate.py) refuses uploads from anyone who
  isn't signed in and invited.
- /local-auth/complete and /local-auth/signout set and clear the session
  cookie for email + password accounts (core/local_auth.py). Streamlit's
  own pages can't set HttpOnly cookies, so a sign-in hands the browser a
  single-use, 2-minute token that it trades here for the cookie.

`streamlit run app.py` still works for local development, without these.
"""
from dotenv import load_dotenv

load_dotenv()

import streamlit as st                          # noqa: E402
from starlette.middleware import Middleware      # noqa: E402
from starlette.responses import RedirectResponse  # noqa: E402
from starlette.routing import Route              # noqa: E402

from core import local_auth                     # noqa: E402
from core.upload_gate import UploadGate         # noqa: E402


def _secure(request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"


async def complete_sign_in(request):
    response = RedirectResponse("/", status_code=303)
    session = local_auth.redeem_login_token(request.query_params.get("token", ""))
    if session:
        token, max_age = session
        response.set_cookie(local_auth.SESSION_COOKIE, token, max_age=max_age, path="/",
                            httponly=True, samesite="lax", secure=_secure(request))
    return response


async def sign_out(request):
    local_auth.end_session(request.cookies.get(local_auth.SESSION_COOKIE, ""))
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(local_auth.SESSION_COOKIE, path="/", httponly=True, samesite="lax",
                           secure=_secure(request))
    return response


app = st.App(
    "app.py",
    middleware=[Middleware(UploadGate)],
    routes=[
        Route("/local-auth/complete", complete_sign_in, methods=["GET"]),
        Route("/local-auth/signout", sign_out, methods=["GET"]),
    ],
)
