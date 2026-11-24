import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import html
import logging
import os
from datetime import datetime, timezone

import streamlit as st

# Import main first: it calls load_dotenv() *before* importing core/, which
# transcriber.py depends on (it reads SARVAM_API_KEY at module import time).
from main import run_pipeline, load_rag_chain, ask_question
from core import db, guardrails, notify, storage, ui, users
from core.auth import require_user, sign_out_href
from core.retriever import reranker_error
from core.settings import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

st.set_page_config(
    page_title="AI Video Assistant",
    page_icon=":material/subtitles:",
    layout="wide",
    initial_sidebar_state="expanded",
)

ui.base_css()


def md(text: str) -> str:
    """
    Streamlit renders $...$ as LaTeX, so an LLM writing "$20 plan ... $100 tier"
    loses everything between the two dollar signs. Escape them.
    """
    return str(text).replace("$", r"\$")


settings = get_settings()
# Stops the script here, showing the sign-in or no-access page, unless the
# visitor is signed in and allowed in.
user = require_user()
# Every read, write and delete below goes through this user's own folder.
space = storage.user_space(user.id)

# A session that switches accounts (sign out, then in as someone else) must
# not keep showing the previous account's meeting or chat.
if st.session_state.get("owner") != user.id:
    st.session_state.owner = user.id
    st.session_state.result = None
    st.session_state.messages = []


def _reset_chat():
    st.session_state.messages = []


# A modal rather than an inline confirm: after a delete the selectbox moves to
# the next meeting, and a confirm button left on screen would then target it.
@st.dialog("Delete meeting?")
def _confirm_delete(filename: str):
    # A dialog is a fragment: clicks inside it rerun only this function, not
    # the top of the script, so check the user again here.
    space = storage.user_space(require_user().id)
    name = filename[:-5]
    st.markdown(f"`{name}` will be removed with its transcript, summary and search index. "
                "This cannot be undone.")
    cancel, confirm = st.columns(2)
    if cancel.button("Cancel", use_container_width=True):
        st.rerun()
    if confirm.button("Delete", type="primary", use_container_width=True):
        try:
            storage.delete_meeting(space, filename)
        except Exception as e:
            st.error(guardrails.user_message(e))
            return
        db.audit("meeting_deleted", user, detail=name)
        # The loaded chain would otherwise query an index that no longer exists.
        if st.session_state.result and st.session_state.result.get("collection_name") == name:
            st.session_state.result = None
            _reset_chat()
        st.toast(f"Deleted {name}", icon=":material/delete:")
        st.rerun()


def _process(url, upload, language: str):
    status = st.status("Starting...", expanded=True)
    try:
        # Every check that costs nothing runs before the download starts.
        if upload is not None:
            input_format = guardrails.validate_upload(upload.name, upload.size)
            ext = os.path.splitext(upload.name)[1].lower()
            display_source = f"Uploaded file: {os.path.basename(upload.name)[:100]}"
        else:
            url = guardrails.validate_video_url(url)
            input_format, display_source = None, url
        guardrails.check_can_start_video(user)

        with guardrails.job_slot(user.id), storage.job_dir(space) as work:
            guardrails.start_attempt(user)
            if upload is not None:
                # A fixed name inside this job's own folder: the user's filename
                # never becomes a path, and two uploads can't overwrite each other.
                source = os.path.join(work, "upload" + ext)
                with open(source, "wb") as f:
                    f.write(upload.getbuffer())
            else:
                source = url
            result = run_pipeline(
                source, language,
                on_step=lambda m: status.update(label=m),
                work_dir=work,
                persist_directory=space.vector_dir,
                input_format=input_format,
                max_minutes=settings.max_video_minutes,
                before_transcribe=lambda minutes: guardrails.charge_video(user, minutes),
            )

        status.update(label="Saving...", state="running")
        storage.save_meeting(space, result, display_source)
        db.audit("video_processed", user,
                 detail=f"{result['collection_name']} ({result['audio_minutes']} min, {language})")
        status.update(label="Done", state="complete", expanded=False)
    except Exception as e:
        status.update(label="Failed", state="error")
        db.audit("video_failed", user, detail=type(e).__name__)
        st.error(guardrails.user_message(e))
        return

    st.session_state.result = result
    _reset_chat()
    st.toast("Meeting saved", icon=":material/check_circle:")
    st.rerun()


def _account_box():
    if settings.auth_mode == "off":
        st.caption("Sign-in is off. Local use on this computer only.")
        return
    st.caption(f"Signed in as {user.email}" + (" (admin)" if user.is_admin else ""))
    if not user.is_admin:
        u = guardrails.usage_summary(user)
        st.caption(
            f"Used today: {u['videos']} of {u['videos_limit']} videos, "
            f"{u['minutes']:.0f} of {u['minutes_limit']} minutes, "
            f"{u['questions']} of {u['questions_limit']} questions."
        )
    if href := sign_out_href():
        # Email accounts: this route deletes the session and clears its cookie.
        # A same-tab link (st.link_button would open a new tab).
        st.markdown(f'<a class="ava-button-link ava-block" href="{href}" target="_self">Sign out</a>',
                    unsafe_allow_html=True)
    else:
        st.button("Sign out", on_click=st.logout, icon=":material/logout:", use_container_width=True)


def _admin_page():
    st.markdown("## Admin")

    if settings.signup_mode == "open":
        st.caption("Anyone can sign up and use the app straight away"
                   + (", and you get an email for each new registration." if notify.enabled() else ".")
                   + " Revoke anyone who looks suspicious; they can't sign up again until you add them back.")

    st.markdown("#### Invite a user")
    with st.form("add_user", clear_on_submit=True):
        c1, c2 = st.columns([3, 1])
        email = c1.text_input("Email")
        role = c2.selectbox("Role", users.ROLES)
        if st.form_submit_button("Add user", type="primary"):
            try:
                is_new = users.add_user(user, email, role, send_invite=True)
                who = users.normalize_email(email)
                told = " We've emailed them a link to sign in." if is_new and notify.enabled() else ""
                st.success(f"{who} can now sign in as {role}.{told}")
            except (ValueError, PermissionError) as e:
                st.error(str(e))

    # Messages from the last action, shown after the rerun that refreshes the tables.
    if done := st.session_state.pop("_admin_done", None):
        st.success(done)

    rows = users.user_details(user)
    st.markdown(f"#### Users ({len(rows)})")
    st.caption("Limits reset at 00:00 UTC. Admins have no daily limits. "
               "Users from ADMIN_EMAILS or ALLOWED_EMAILS are changed in .env.")

    def when(ts):
        return datetime.fromtimestamp(ts, timezone.utc).strftime("%d %b %Y, %H:%M") if ts else ""

    st.dataframe(
        [
            {
                "Name": r["name"],
                "Email": r["email"],
                "Role": r["role"],
                "Added via": r["source"],
                "Signs in with": r["method"],
                "Joined (UTC)": when(r["joined"]),
                "Last sign-in (UTC)": when(r["last_sign_in"]),
                "Meetings": r["meetings"],
                "Videos today": int(r["today"].get("video", 0)),
                "Questions today": int(r["today"].get("question", 0)),
                "Videos total": int(r["total"].get("video", 0)),
                "Audio min total": round(r["total"].get("audio_minutes", 0)),
                "Questions total": int(r["total"].get("question", 0)),
            }
            for r in rows
        ],
        hide_index=True, use_container_width=True,
    )

    fixed = settings.admin_emails | settings.allowed_emails
    manageable = {r["email"]: r for r in rows if r["email"] != user.email and r["email"] not in fixed}
    st.markdown("#### Manage a user")
    if not manageable:
        st.caption("Nobody to manage yet. People who sign up or are invited appear here.")
    else:
        target = st.selectbox("User", list(manageable), format_func=lambda e: users.label(manageable[e]),
                              key="manage_target")
        picked = manageable[target]
        st.caption(f"{picked['role'].capitalize()} · signs in with {picked['method']} · "
                   f"{picked['meetings']} meeting{'s' if picked['meetings'] != 1 else ''}")
        who = users.label(picked)

        def act(fn, message):
            try:
                fn()
                st.session_state["_admin_done"] = message
                st.rerun()
            except (ValueError, PermissionError) as e:
                st.error(str(e))

        c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
        new_role = c1.selectbox("Role", users.ROLES, index=users.ROLES.index(picked["role"]),
                                key=f"role_{target}")
        if c2.button("Save role", use_container_width=True, disabled=new_role == picked["role"]):
            act(lambda: users.set_role(user, target, new_role), f"{who} is now {new_role}.")

        if st.button("Revoke access", icon=":material/block:", key="revoke_user"):
            act(lambda: users.remove_user(user, target),
                f"{who} can no longer sign in or sign up again. Their meetings stay on disk; "
                "restore them under Revoked emails.")

        with st.expander("Delete this user and all their data"):
            st.caption("Removes their account, sign-in sessions, usage counts, and every meeting and "
                       "search index. This can't be undone. The audit log keeps its record.")
            block = st.checkbox("Also stop this email signing up again", value=True, key="delete_block")
            sure = st.checkbox(f"Yes, permanently delete {who}", key="delete_sure")
            if st.button("Delete user", type="primary", disabled=not sure, key="delete_user"):
                act(lambda: users.delete_user(user, target, block=block),
                    f"{who} and all their meetings were deleted.")

    revoked = users.list_revoked(user)
    if revoked:
        st.markdown(f"#### Revoked emails ({len(revoked)})")
        st.caption("They can't sign in or sign up. Restoring one gives them access again as a regular user.")
        st.dataframe(
            [{"Name": r["name"], "Email": r["email"], "Revoked (UTC)": when(r["revoked_at"]),
              "By": r["decided_by"] or ""} for r in revoked],
            hide_index=True, use_container_width=True,
        )
        by_email = {r["email"]: r for r in revoked}
        c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
        back = c1.selectbox("Revoked email", list(by_email), format_func=lambda e: users.label(by_email[e]),
                            key="restore_target")
        if c2.button("Restore", use_container_width=True, key="restore_user"):
            try:
                users.restore_user(user, back)
                st.session_state["_admin_done"] = f"{users.label(by_email[back])} can use the app again."
                st.rerun()
            except (ValueError, PermissionError) as e:
                st.error(str(e))

    st.markdown("#### Audit log")
    st.caption("Latest 200 events. Questions and transcripts are never logged.")
    st.dataframe(
        [
            {
                "Time (UTC)": datetime.fromtimestamp(r["ts"], timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                "Email": r["email"],
                "Action": r["action"],
                "Detail": r["detail"],
            }
            for r in db.recent_audit(200)
        ],
        hide_index=True, use_container_width=True,
    )


# Sidebar controls for sources, processing, and saved meetings.
with st.sidebar:
    st.markdown(ui.BRAND, unsafe_allow_html=True)
    _account_box()
    st.divider()

    modes = ["New video", "Saved meetings"] + (["Admin"] if user.is_admin else [])
    mode = st.radio("Source", modes, label_visibility="collapsed")

    if mode == "New video":
        if settings.enable_youtube:
            kind = st.segmented_control("Input", ["YouTube URL", "Upload file"], default="YouTube URL")
        else:
            # Upload-only server: YouTube blocks cloud servers, so don't offer
            # an option that would fail.
            kind = "Upload file"

        url = upload = None
        if kind == "YouTube URL":
            url = st.text_input("YouTube URL", placeholder="https://www.youtube.com/watch?v=...",
                                key="youtube_url", max_chars=300)
            ready = bool(url.strip())
        else:
            upload = st.file_uploader("Audio or video file", type=list(guardrails.UPLOAD_FORMATS))
            ready = upload is not None
        st.caption(f"Up to {settings.max_video_minutes} minutes"
                   + (f" and {settings.max_upload_mb} MB." if kind != "YouTube URL" else "."))
        if not settings.enable_youtube:
            st.caption("For a YouTube video, save its audio as a file first, then upload it here.")

        ENGINES = {
            "english":  ("English (Deepgram)",        "Cloud transcription. The fastest option."),
            "hinglish": ("Hinglish (Sarvam)",         "Cloud. Turns Hindi-English speech into an English transcript."),
            "whisper":  ("English (Whisper, local)",  "Runs on the server's CPU. Slow, with no cloud service."),
        }
        if not settings.enable_whisper:
            del ENGINES["whisper"]
        language = st.selectbox(
            "Engine",
            list(ENGINES),
            format_func=lambda x: ENGINES[x][0],
        )
        st.caption(ENGINES[language][1])

        if st.button("Process video", type="primary", use_container_width=True, disabled=not ready):
            _process(url, upload, language)

    elif mode == "Saved meetings":
        saved = storage.list_meetings(space)
        if not saved:
            st.info("No saved meetings yet. Process a video first.")
        else:
            pick = st.selectbox("Meeting", saved, format_func=lambda f: f[:-5])
            if st.button("Open meeting", type="primary", use_container_width=True):
                try:
                    with st.spinner("Opening meeting..."):
                        r = storage.load_meeting(space, pick)
                        r["rag_chain"] = load_rag_chain(r["collection_name"], r["transcript"],
                                                        persist_directory=space.vector_dir)
                except Exception as e:
                    st.error(guardrails.user_message(e))
                else:
                    st.session_state.result = r
                    _reset_chat()
                    db.audit("meeting_opened", user, detail=pick[:-5])
                    st.rerun()
            if st.button("Delete meeting", use_container_width=True):
                _confirm_delete(pick)

    else:
        st.caption("Invite users, revoke access, and review usage and the audit log.")

    if st.session_state.result:
        st.divider()
        if st.button("Clear", use_container_width=True):
            st.session_state.result = None
            _reset_chat()
            st.rerun()

    st.markdown(ui.theme_toggle(label=True), unsafe_allow_html=True)
    st.markdown(ui.credit_line(), unsafe_allow_html=True)


if mode == "Admin":
    # Offered only to admins above; users.* checks the role again.
    _admin_page()
    st.stop()


# Main panel for the loaded meeting, transcript, summary, and chat.
result = st.session_state.result

if result is None:
    how = ("Paste a YouTube link or upload a recording" if settings.enable_youtube
           else "Upload a recording")
    st.markdown(
        f'<div class="ava-empty"><h2>Open a video to get started</h2>'
        f"<p>{how} in the sidebar, or open one of your saved meetings.</p></div>",
        unsafe_allow_html=True,
    )
    st.stop()


def _saved_label(saved_at) -> str:
    if not saved_at:
        return "Saved just now"
    try:
        return "Saved " + datetime.fromisoformat(saved_at).strftime("%d %b %Y, %H:%M")
    except ValueError:
        return f"Saved {saved_at}"


# The title comes from the LLM and the source is user-supplied (both are
# persisted and re-rendered on every reload), so escape before building HTML.
st.markdown(f'<h1 class="ava-title">{html.escape(result["title"])}</h1>', unsafe_allow_html=True)
source = result.get("source", "")
if source.startswith(("http://", "https://")):
    source_html = f'From <a href="{html.escape(source)}" target="_blank" rel="noopener">{html.escape(source)}</a>'
else:
    source_html = html.escape(source)
st.markdown(
    f'<p class="ava-meta">{source_html}<br>{html.escape(_saved_label(result.get("saved_at")))}</p>',
    unsafe_allow_html=True,
)

transcript = result["transcript"]
c1, c2, c3 = st.columns(3)
c1.metric("Words", f"{len(transcript.split()):,}")
c2.metric("Characters", f"{len(transcript):,}")
c3.metric("Reading time", f"{max(1, len(transcript.split()) // 200)} min")

tabs = st.tabs(["Summary", "Transcript"])

with tabs[0]:
    with st.container(key="reading_summary"):
        # The summary is LLM output over an untrusted transcript, like an answer.
        st.markdown(md(guardrails.clean_answer(result["summary"])))
with tabs[1]:
    with st.container(key="reading_transcript"):
        st.download_button("Download transcript", transcript, icon=":material/download:",
                           file_name=f"{result['collection_name']}.txt", mime="text/plain")
        st.text_area("Full transcript", transcript, height=420, label_visibility="collapsed")

st.divider()
st.markdown("### Ask about this meeting")
if err := reranker_error():
    # The load error can include server paths, so only admins see it.
    detail = f" ({md(err)})" if user.is_admin else ""
    st.warning("Reranker unavailable, so answers use hybrid search ranking only. "
               f"It retries when you next load or process a meeting.{detail}")
else:
    st.caption("Answers come only from this video. Follow-up questions use the last 3 exchanges.")

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(md(m["content"]))

if q := st.chat_input("Ask a question about this meeting", max_chars=settings.max_question_chars):
    # Failed turns stay on screen but aren't sent back: an error text would
    # read to the model as something it said, and the question got no answer.
    history = [m for m in st.session_state.messages if not m.get("failed")]
    st.session_state.messages.append({"role": "user", "content": q})
    with st.chat_message("user"):
        st.markdown(md(q))
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            failed = False
            try:
                question = guardrails.check_question(user, q)
                a = guardrails.clean_answer(ask_question(result["rag_chain"], question, history))
            except Exception as e:
                a, failed = f"No answer: {guardrails.user_message(e)}", True
        st.markdown(md(a))
    if failed:
        st.session_state.messages[-1]["failed"] = True
    st.session_state.messages.append({"role": "assistant", "content": a, "failed": failed})
