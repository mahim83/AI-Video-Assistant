"""
Production entry point: the same app as app.py, with the upload gate in
front of Streamlit (see core/upload_gate.py). Start it the usual way:

    streamlit run server.py

`streamlit run app.py` still works for local development; it just runs
without the gate.
"""
from dotenv import load_dotenv

load_dotenv()

import streamlit as st                      # noqa: E402
from starlette.middleware import Middleware  # noqa: E402

from core.upload_gate import UploadGate     # noqa: E402

app = st.App("app.py", middleware=[Middleware(UploadGate)])
