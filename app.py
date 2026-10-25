import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import os
import json
import html
import streamlit as st

# Import main first: it calls load_dotenv() *before* importing core/, which
# transcriber.py depends on (it reads SARVAM_API_KEY at module import time).
from main import (
    run_pipeline,
    save_result,
    list_saved,
    load_saved,
    delete_saved,
    load_rag_chain,
    ask_question,
)
from utils.audio_processor import DOWNLOAD_DIR
from core.retriever import reranker_error

st.set_page_config(
    page_title="AI Video Assistant",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  .block-container { padding-top: 2.2rem; max-width: 1100px; }
  [data-testid="stMetricValue"] { font-size: 1.35rem; }
  .meeting-title {
      font-size: 1.9rem; font-weight: 700; line-height: 1.25; margin: 0 0 .15rem 0;
  }
  .meeting-sub { opacity: .6; font-size: .88rem; margin-bottom: 1.1rem; }
  .empty-hero { text-align: center; padding: 3.5rem 1rem; opacity: .75; }
  .empty-hero h2 { font-weight: 650; margin-bottom: .4rem; }
  .st-key-youtube_url [data-testid="InputInstructions"] { display: none; }
</style>
""", unsafe_allow_html=True)


def md(text: str) -> str:
    """
    Streamlit renders $...$ as LaTeX, so an LLM writing "$20 plan ... $100 tier"
    loses everything between the two dollar signs. Escape them.
    """
    return str(text).replace("$", r"\$")


# State for the active meeting and its chat.
st.session_state.setdefault("result", None)
st.session_state.setdefault("messages", [])


def _reset_chat():
    st.session_state.messages = []


# A modal rather than an inline confirm: after a delete the selectbox moves to
# the next meeting, and a confirm button left on screen would then target it.
@st.dialog("Delete meeting?")
def _confirm_delete(filename: str):
    name = filename[:-5]
    st.markdown(f"`{name}` will be removed with its transcript, summary, search index "
                "and downloaded audio. This cannot be undone.")
    cancel, confirm = st.columns(2)
    if cancel.button("Cancel", use_container_width=True):
        st.rerun()
    if confirm.button("Delete", type="primary", use_container_width=True):
        try:
            delete_saved(filename)
        except Exception as e:
            st.error(f"{type(e).__name__}: {e}")
            return
        # The loaded chain would otherwise query an index that no longer exists.
        if st.session_state.result and st.session_state.result.get("collection_name") == name:
            st.session_state.result = None
            _reset_chat()
        st.toast(f"Deleted {name}", icon="🗑️")
        st.rerun()


# Sidebar controls for sources, processing, and saved meetings.
with st.sidebar:
    st.markdown("### 🎬 AI Video Assistant")
    st.caption("Transcribe, summarise and interrogate any meeting or video.")
    st.divider()

    mode = st.radio("Source", ["New video", "Saved meetings"], label_visibility="collapsed")

    if mode == "New video":
        kind = st.segmented_control("Input", ["YouTube URL", "Upload file"], default="YouTube URL")

        source = None
        if kind == "YouTube URL":
            url = st.text_input("YouTube URL", placeholder="https://www.youtube.com/watch?v=...", key="youtube_url")
            source = url.strip() or None
        else:
            upload = st.file_uploader("Audio or video file", type=["mp3", "wav", "m4a", "mp4", "mkv", "webm", "aac"])
            if upload is not None:
                os.makedirs(DOWNLOAD_DIR, exist_ok=True)
                # basename strips any directory components (e.g. "../../x.mp4")
                # a crafted filename could carry, so the write can't escape DOWNLOAD_DIR.
                source = os.path.join(DOWNLOAD_DIR, os.path.basename(upload.name))
                with open(source, "wb") as f:
                    f.write(upload.getbuffer())

        ENGINES = {
            "english":  ("English — Deepgram",      "☁️ Cloud, fast. Uses your Deepgram quota."),
            "hinglish": ("Hinglish — Sarvam",       "☁️ Cloud. Translates Hindi-English to English."),
            "whisper":  ("English — Whisper (local)", "⏱️ Runs on your CPU. Slow and warms the laptop, but free and offline."),
        }
        language = st.selectbox(
            "Engine",
            list(ENGINES),
            format_func=lambda x: ENGINES[x][0],
        )
        st.caption(ENGINES[language][1])

        go = st.button("Process video", type="primary", use_container_width=True, disabled=not source)

        if go and source:
            status = st.status("Starting...", expanded=True)
            try:
                result = run_pipeline(source, language, on_step=lambda m: status.update(label=m))
                status.update(label="Saving...", state="running")
                path = save_result(result, source)
                status.update(label="Done", state="complete", expanded=False)
                st.session_state.result = result
                _reset_chat()
                st.toast(f"Saved to {path}", icon="💾")
                st.rerun()
            except Exception as e:
                status.update(label="Failed", state="error")
                st.error(f"{type(e).__name__}: {e}")

    else:
        saved = list_saved()
        if not saved:
            st.info("No saved meetings yet. Process a video first.")
        else:
            pick = st.selectbox("Meeting", saved, format_func=lambda f: f[:-5])
            if st.button("Load meeting", type="primary", use_container_width=True):
                with st.spinner("Reopening saved index..."):
                    r = load_saved(pick)
                    r["rag_chain"] = load_rag_chain(r["collection_name"], r["transcript"])
                    st.session_state.result = r
                    _reset_chat()
                st.rerun()
            if st.button("Delete meeting", use_container_width=True):
                _confirm_delete(pick)

    if st.session_state.result:
        st.divider()
        if st.button("Clear", use_container_width=True):
            st.session_state.result = None
            _reset_chat()
            st.rerun()


# Main panel for the loaded meeting, transcript, summary, and chat.
result = st.session_state.result

if result is None:
    st.markdown("""
      <div class="empty-hero">
                <h2>🎬 Nothing loaded yet</h2>
                <p>Paste a YouTube link in the sidebar, or reopen a saved meeting.</p>
      </div>
    """, unsafe_allow_html=True)
    st.stop()


# The title comes from the LLM and the source is user-supplied (both are
# persisted and re-rendered on every reload), so escape before building HTML.
st.markdown(f'<div class="meeting-title">{html.escape(result["title"])}</div>', unsafe_allow_html=True)
meta = result.get("saved_at", "just now")
source = html.escape(result.get("source", ""))
st.markdown(f'<div class="meeting-sub">{source} · {meta}</div>', unsafe_allow_html=True)

transcript = result["transcript"]
c1, c2, c3 = st.columns(3)
c1.metric("Words", f"{len(transcript.split()):,}")
c2.metric("Characters", f"{len(transcript):,}")
c3.metric("Est. read time", f"{max(1, len(transcript.split()) // 200)} min")

tabs = st.tabs(["📋 Summary", "📝 Transcript"])

with tabs[0]:
    st.markdown(md(result["summary"]))
with tabs[1]:
    st.download_button("Download transcript (.txt)", transcript,
                       file_name=f"{result['collection_name']}.txt", mime="text/plain")
    st.text_area("Full transcript", transcript, height=420, label_visibility="collapsed")

st.divider()
st.markdown("### 💬 Chat with this meeting")
if err := reranker_error():
    st.warning("Reranker unavailable, so answers use hybrid search ranking only. "
               f"It retries when you next load or process a meeting. ({md(err)})")
else:
    st.caption("Retrieval: vector + BM25 hybrid search, reranked by a cross-encoder. "
               "Follow-up questions use the last 3 exchanges.")

for m in st.session_state.messages:
    with st.chat_message(m["role"], avatar="🤖" if m["role"] == "assistant" else None):
        st.markdown(md(m["content"]))

if q := st.chat_input("Ask anything about this meeting..."):
    # Failed turns stay on screen but aren't sent back: an error text would
    # read to the model as something it said, and the question got no answer.
    history = [m for m in st.session_state.messages if not m.get("failed")]
    st.session_state.messages.append({"role": "user", "content": q})
    with st.chat_message("user"):
        st.markdown(md(q))
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("Thinking..."):
            failed = False
            try:
                a = ask_question(result["rag_chain"], q, history)
            except Exception as e:
                a, failed = f"⚠️ {type(e).__name__}: {e}", True
        st.markdown(md(a))
    if failed:
        st.session_state.messages[-1]["failed"] = True
    st.session_state.messages.append({"role": "assistant", "content": a, "failed": failed})
