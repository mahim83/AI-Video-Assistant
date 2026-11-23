"""
Look and feel: design tokens, shared CSS, and the signed-out pages.

Direction "Caption track": the transcript is the product, so the pages are
typeset like one. Bricolage Grotesque (set in .streamlit/config.toml) carries
the interface; Newsreader carries anything meant to be read: transcripts,
summaries and answers. One accent, deep teal, marks what you can act on.
"""
import html

import streamlit as st

# A caption frame: the screen outline with two subtitle lines.
BRAND_MARK = (
    '<svg class="ava-mark" viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" '
    'fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
    '<rect x="2.5" y="4" width="19" height="16" rx="3"/>'
    '<path d="M6.5 13.5h6M15 13.5h2.5M6.5 16.5h3.5M12.5 16.5h5"/></svg>'
)

BRAND = f'<div class="ava-brand">{BRAND_MARK}<span>AI Video Assistant</span></div>'

# Google's "G", shown in a white disc on the sign-in button.
_GOOGLE_G = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 48 48'%3E"
    "%3Cpath fill='%23EA4335' d='M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 "
    "14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z'/%3E"
    "%3Cpath fill='%234285F4' d='M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 "
    "5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z'/%3E"
    "%3Cpath fill='%23FBBC05' d='M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19"
    "C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z'/%3E"
    "%3Cpath fill='%2334A853' d='M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 "
    "2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z'/%3E%3C/svg%3E"
)

BASE_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,500&display=swap');

:root {
  --ava-surface: #F4F6F8;
  --ava-raised: #FFFFFF;
  --ava-ink: #1C2733;
  --ava-muted: #5B6875;
  --ava-faint: #8A96A3;
  --ava-rule: #D8DEE5;
  --ava-accent: #0E7C6B;
  --ava-accent-strong: #0A6658;
  --ava-read: 'Newsreader', Georgia, serif;
}

.block-container { padding-top: 2.5rem; max-width: 1100px; }
[data-testid="stMetricValue"] { font-size: 1.5rem; font-variant-numeric: tabular-nums; }
[data-testid="stMetricLabel"] p { color: var(--ava-muted); }

/* Brand */
.ava-brand { display: flex; align-items: center; gap: .55rem; font-weight: 600;
             font-size: 1rem; color: var(--ava-ink); letter-spacing: -.005em; }
.ava-mark { color: var(--ava-accent); flex: none; }

/* Headings below are written as [data-testid] h1.class: Streamlit styles
   markdown headings itself, and a bare class selector loses to that. */

/* Meeting header */
[data-testid="stMarkdownContainer"] h1.ava-title { font-size: 2rem; font-weight: 600; line-height: 1.15; letter-spacing: -.018em;
             margin: 0 0 .35rem 0; padding: 0; color: var(--ava-ink); max-width: 46rem; }
.ava-meta { color: var(--ava-muted); font-size: .875rem; margin: 0 0 1.5rem 0; }
.ava-meta a { color: var(--ava-muted); text-decoration: underline; text-underline-offset: 2px; }

/* Empty state */
.ava-empty { max-width: 34rem; padding: 3.5rem 0 2rem; }
[data-testid="stMarkdownContainer"] .ava-empty h2 { font-size: 1.5rem; font-weight: 600; letter-spacing: -.012em;
                margin: 0 0 .5rem 0; padding: 0; }
.ava-empty p { color: var(--ava-muted); font-size: 1.0625rem; line-height: 1.55; margin: 0; }

/* Reading text: summaries, transcripts and chat answers. */
.st-key-reading_summary, .st-key-reading_transcript { max-width: 46rem; }
.st-key-reading_summary [data-testid="stMarkdownContainer"] :is(p, li),
.st-key-reading_transcript textarea,
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] :is(p, li) {
  font-family: var(--ava-read); font-size: 1.0625rem; line-height: 1.62;
}
.st-key-reading_summary [data-testid="stMarkdownContainer"] :is(h1, h2, h3) {
  font-size: 1.25rem; letter-spacing: -.01em;
}
[data-testid="stChatMessage"] { max-width: 50rem; }

/* Motion: quick and only in response to the person. */
button { transition: background-color 150ms ease-out, border-color 150ms ease-out, color 150ms ease-out; }

.st-key-youtube_url [data-testid="InputInstructions"] { display: none; }
</style>
"""

SIGNED_OUT_CSS = """
<style>
.ava-signedout { padding-top: 2.5rem; }
.ava-signedout .ava-brand { margin-bottom: 3rem; }
[data-testid="stMarkdownContainer"] h1.ava-headline { font-size: clamp(2.25rem, 1.55rem + 2.4vw, 3.25rem); font-weight: 600;
                line-height: 1.06; letter-spacing: -.024em; color: var(--ava-ink);
                margin: 0 0 1.25rem 0; padding: 0; max-width: 15ch; }
[data-testid="stMarkdownContainer"] h1.ava-headline.ava-wide { max-width: 21ch; }
.ava-lede { font-size: 1.1875rem; line-height: 1.55; color: var(--ava-muted);
            margin: 0 0 2rem 0; max-width: 34rem; }
.ava-note { font-size: .875rem; line-height: 1.5; color: var(--ava-muted);
            margin: 1.25rem 0 0 0; max-width: 30rem; }

/* Primary actions on the signed-out pages. */
:is(.st-key-google_signin, .st-key-google_register, .st-key-switch_account, .st-key-request_access, .st-key-request_check) button {
  width: auto; min-width: 16rem; min-height: 3rem; padding: 0 1.25rem;
  background: var(--ava-accent); border-color: var(--ava-accent); color: #fff;
}
:is(.st-key-google_signin, .st-key-google_register) button { padding-left: .75rem; }
:is(.st-key-google_signin, .st-key-google_register, .st-key-switch_account, .st-key-request_access, .st-key-request_check) button:hover {
  background: var(--ava-accent-strong); border-color: var(--ava-accent-strong); color: #fff;
}
:is(.st-key-google_signin, .st-key-google_register, .st-key-switch_account, .st-key-request_access, .st-key-request_check) button:focus-visible {
  outline: 2px solid var(--ava-accent); outline-offset: 3px;
}
:is(.st-key-google_signin, .st-key-google_register, .st-key-switch_account, .st-key-request_access, .st-key-request_check) button p {
  font-size: 1rem; font-weight: 600;
}

/* Sign in / Register tabs. */
.st-key-signin_tabs [role="tablist"] { gap: 1.75rem; margin-bottom: .5rem; }
.st-key-signin_tabs [data-testid="stTab"] p { font-size: 1rem; font-weight: 600; }
.ava-steps { margin: .25rem 0 1.5rem 0; padding-left: 1.25rem; color: var(--ava-muted);
             font-size: 1rem; line-height: 1.6; max-width: 34rem; }
.ava-steps li { margin: 0 0 .35rem 0; padding-left: .25rem; }
.ava-steps li::marker { color: var(--ava-accent); font-weight: 600; }
.ava-tab-lede { color: var(--ava-muted); font-size: 1rem; line-height: 1.55; margin: .25rem 0 1.25rem 0;
                max-width: 34rem; }

:is(.st-key-google_signin, .st-key-google_register) button::before {
  content: ""; flex: none; width: 1.75rem; height: 1.75rem; margin-right: .75rem;
  border-radius: 50%; background: #fff url("__GOOGLE_G__") center / 1.05rem no-repeat;
}

/* One column: these pages say one thing each. */
.st-key-signedout { max-width: 40rem; }

/* The one orchestrated moment: the headline arrives word by word, the way
   live captions do, then the explanation and the action follow. Once, on load,
   about a second in all; switched off for anyone who prefers reduced motion. */
@keyframes ava-rise { from { opacity: 0; transform: translateY(.28em); } to { opacity: 1; transform: none; } }
.ava-caption .ava-w { display: inline-block; animation: ava-rise 220ms ease-out both; }
.ava-caption .ava-w:nth-child(2)  { animation-delay: 70ms; }
.ava-caption .ava-w:nth-child(3)  { animation-delay: 140ms; }
.ava-caption .ava-w:nth-child(4)  { animation-delay: 210ms; }
.ava-caption .ava-w:nth-child(5)  { animation-delay: 280ms; }
.ava-caption .ava-w:nth-child(6)  { animation-delay: 350ms; }
.ava-caption .ava-w:nth-child(7)  { animation-delay: 420ms; }
.ava-caption .ava-w:nth-child(8)  { animation-delay: 490ms; }
.ava-caption .ava-w:nth-child(9)  { animation-delay: 560ms; }
.ava-caption .ava-w:nth-child(10) { animation-delay: 630ms; }
.ava-follow { animation: ava-rise 240ms ease-out 700ms both; }
.st-key-signin_tabs { animation: ava-rise 240ms ease-out 820ms both; }
@media (prefers-reduced-motion: reduce) {
  .ava-caption .ava-w, .ava-follow, .st-key-signin_tabs { animation: none; }
}

@media (max-width: 640px) {
  .ava-signedout { padding-top: .5rem; }
  .ava-signedout .ava-brand { margin-bottom: 2rem; }
}
</style>
""".replace("__GOOGLE_G__", _GOOGLE_G)


def _caption_words(text: str) -> str:
    """Wrap each word so the headline can arrive word by word."""
    return " ".join(f'<span class="ava-w">{html.escape(w)}</span>' for w in text.split())


def base_css():
    st.markdown(BASE_CSS, unsafe_allow_html=True)


def _header(headline: str, lede_html: str, caption: bool = False, wide: bool = False):
    words = _caption_words(headline) if caption else html.escape(headline)
    classes = "ava-headline" + (" ava-caption" if caption else "") + (" ava-wide" if wide else "")
    st.markdown(
        f'<div class="ava-signedout">{BRAND}<h1 class="{classes}">{words}</h1>'
        f'<p class="ava-lede{" ava-follow" if caption else ""}">{lede_html}</p></div>',
        unsafe_allow_html=True,
    )


def _note(text: str, follow: bool = False):
    st.markdown(f'<p class="ava-note{" ava-follow" if follow else ""}">{text}</p>', unsafe_allow_html=True)


def sign_in_page():
    from core import notify
    from core.settings import get_settings
    settings = get_settings()
    how = ("Paste a YouTube link or upload a recording." if settings.enable_youtube
           else "Upload a recording of a meeting, lecture or video.")
    st.markdown(SIGNED_OUT_CSS, unsafe_allow_html=True)
    with st.container(key="signedout"):
        _header("Ask questions about any video or meeting recording.",
                f"{how} You get the full transcript, a short summary, "
                "and answers drawn from what was actually said.", caption=True)

        with st.container(key="signin_tabs"):
            sign_in, register = st.tabs(["Sign in", "Register"])
            with sign_in:
                st.markdown('<p class="ava-tab-lede">Already approved? Sign in with the Google '
                            "account you registered with.</p>", unsafe_allow_html=True)
                st.button("Continue with Google", key="google_signin", on_click=st.login)
                _note("Your meetings are private: other users can't see them.")
            with register:
                if settings.signup_mode == "request":
                    last = ("You'll get an email when you're approved, then sign in."
                            if notify.enabled() else "Once you're approved, sign in.")
                    st.markdown(
                        '<ol class="ava-steps">'
                        "<li>Continue with the Google account you want to use.</li>"
                        "<li>Click <strong>Request access</strong>.</li>"
                        f"<li>The admin reviews your request. {last}</li></ol>",
                        unsafe_allow_html=True,
                    )
                    st.button("Register with Google", key="google_register", on_click=st.login)
                    _note("Google only shares your name and email address with this app. "
                          "No password is stored here.")
                else:
                    st.markdown('<p class="ava-tab-lede">Accounts are by invitation. Ask the person '
                                "who runs this app to add your Google account, then sign in.</p>",
                                unsafe_allow_html=True)


def request_page(email: str, status, on_request, on_request_args=(), error: str = None):
    """For a verified Google account that isn't on the list yet."""
    who = html.escape(email, quote=False)
    st.markdown(SIGNED_OUT_CSS, unsafe_allow_html=True)
    with st.container(key="signedout"):
        if status == "pending":
            from core import notify
            then = (f"You'll get an email at {who} when it's approved."
                    if notify.enabled() else "You can use the app as soon as it's approved.")
            _header("Request sent.", f"Your request for {who} is waiting for the admin's approval. "
                    f"{then}", wide=True)
            st.button("Check again", key="request_check")
        else:
            _header("Request access.", f"You're signed in as {who}. This app is invite only: "
                    "send a request and the admin will review it.", wide=True)
            st.button("Request access", key="request_access", on_click=on_request, args=on_request_args)
        if error:
            st.error(error)
        st.button("Use a different account", key="switch_account_plain", on_click=st.logout)


def denied_page(message: str):
    st.markdown(SIGNED_OUT_CSS, unsafe_allow_html=True)
    with st.container(key="signedout"):
        # Escaped: the message contains the email the visitor signed in with.
        _header("This account doesn't have access.", html.escape(message, quote=False), wide=True)
        st.button("Use a different account", key="switch_account", on_click=st.logout)
        _note("You'll be signed out and can choose another Google account.")
