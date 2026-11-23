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

.st-key-google_signin button, .st-key-switch_account button {
  width: auto; min-width: 16rem; min-height: 3rem; padding: 0 1.25rem 0 .75rem;
  background: var(--ava-accent); border-color: var(--ava-accent); color: #fff;
}
.st-key-switch_account button { padding: 0 1.25rem; }
.st-key-google_signin button:hover, .st-key-switch_account button:hover {
  background: var(--ava-accent-strong); border-color: var(--ava-accent-strong); color: #fff;
}
.st-key-google_signin button:focus-visible, .st-key-switch_account button:focus-visible {
  outline: 2px solid var(--ava-accent); outline-offset: 3px;
}
.st-key-google_signin button p, .st-key-switch_account button p { font-size: 1rem; font-weight: 600; }
.st-key-google_signin button::before {
  content: ""; flex: none; width: 1.75rem; height: 1.75rem; margin-right: .75rem;
  border-radius: 50%; background: #fff url("__GOOGLE_G__") center / 1.05rem no-repeat;
}

/* The excerpt: transcript, the summary point drawn from it, and a question about it. */
/* Pushed down so the panel's top lines up with the headline, not the brand. */
.ava-excerpt-col { padding-top: 8.7rem; }
.st-key-denied { max-width: 40rem; }
.ava-excerpt { background: var(--ava-raised); border: 1px solid #E3E8ED; border-radius: .75rem;
               padding: .5rem 1.75rem 1.25rem; margin: 0; }
.ava-row { display: grid; grid-template-columns: 5.25rem 1fr; gap: 1.25rem; padding: 1.15rem 0;
           border-top: 1px solid var(--ava-rule); }
.ava-row:first-child { border-top: 0; }
.ava-label { font-size: .8125rem; font-weight: 500; color: var(--ava-faint); padding-top: .2rem; }
.ava-text p { font-family: var(--ava-read); font-size: 1.0625rem; line-height: 1.6;
              color: var(--ava-ink); margin: 0 0 .5rem 0; }
.ava-text p:last-child { margin-bottom: 0; }
.ava-text .ava-q { font-family: inherit; font-size: 1rem; font-weight: 600; line-height: 1.45; }
.ava-excerpt figcaption { font-size: .8125rem; color: var(--ava-faint); padding-top: .9rem;
                          border-top: 1px solid var(--ava-rule); }

/* One orchestrated moment: the excerpt plays in like captions, once. */
@keyframes ava-caption { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
.ava-cue { animation: ava-caption 200ms ease-out both; }
.ava-cue:nth-of-type(2) { animation-delay: 180ms; }
.ava-cue:nth-of-type(3) { animation-delay: 360ms; }
.ava-row:nth-child(2) .ava-cue { animation-delay: 620ms; }
.ava-row:nth-child(3) .ava-cue:nth-of-type(1) { animation-delay: 860ms; }
.ava-row:nth-child(3) .ava-cue:nth-of-type(2) { animation-delay: 1040ms; }
@media (prefers-reduced-motion: reduce) { .ava-cue { animation: none; } }

@media (max-width: 640px) {
  .ava-signedout { padding-top: .5rem; }
  .ava-signedout .ava-brand { margin-bottom: 2rem; }
  .ava-excerpt-col { padding-top: .5rem; }
  .ava-excerpt { padding: .25rem 1.1rem 1rem; }
  .ava-row { grid-template-columns: 1fr; gap: .35rem; }
}
</style>
""".replace("__GOOGLE_G__", _GOOGLE_G)

# A real passage from a processed 50-minute video, with the summary point and
# answer written from what the speaker says there.
EXCERPT = """
<div class="ava-excerpt-col">
<figure class="ava-excerpt">
  <div class="ava-row">
    <div class="ava-label">Transcript</div>
    <div class="ava-text">
      <p class="ava-cue">Every LLM is trained on a particular date, so it has information up to a particular date.</p>
      <p class="ava-cue">If I'm using GPT and it has information till October 2023, then it doesn't have access to the latest information.</p>
      <p class="ava-cue">They are good at answering questions, but they don't really perform any task.</p>
    </div>
  </div>
  <div class="ava-row">
    <div class="ava-label">Summary</div>
    <div class="ava-text">
      <p class="ava-cue">LLM apps hit two limits: knowledge that stops at the training date, and models that write text instead of carrying out tasks.</p>
    </div>
  </div>
  <div class="ava-row">
    <div class="ava-label">Ask</div>
    <div class="ava-text">
      <p class="ava-cue ava-q">What problems does the speaker see with LLM apps?</p>
      <p class="ava-cue">Two: the model only knows what existed up to its training date, and it can only produce text, so it can't act on its own.</p>
    </div>
  </div>
  <figcaption>From a 50-minute talk on MCP architecture, processed with this app.</figcaption>
</figure>
</div>
"""


def base_css():
    st.markdown(BASE_CSS, unsafe_allow_html=True)


def sign_in_page():
    from core.settings import get_settings
    how = ("Paste a YouTube link or upload a recording." if get_settings().enable_youtube
           else "Upload a recording of a meeting, lecture or video.")
    st.markdown(SIGNED_OUT_CSS, unsafe_allow_html=True)
    left, right = st.columns([5, 6], gap="large")
    with left:
        st.markdown(
            f'<div class="ava-signedout">{BRAND}'
            '<h1 class="ava-headline">Ask questions about any video or meeting recording.</h1>'
            f'<p class="ava-lede">{how} You get the full transcript, a short summary, '
            "and answers drawn from what was actually said.</p></div>",
            unsafe_allow_html=True,
        )
        st.button("Continue with Google", key="google_signin", on_click=st.login)
        st.markdown(
            '<p class="ava-note">This app is invite only. Ask the person who runs it to add your '
            "Google account. Other users can't see your meetings.</p>",
            unsafe_allow_html=True,
        )
    with right:
        st.markdown(EXCERPT, unsafe_allow_html=True)


def denied_page(message: str):
    st.markdown(SIGNED_OUT_CSS, unsafe_allow_html=True)
    with st.container(key="denied"):
        st.markdown(
            f'<div class="ava-signedout">{BRAND}'
            '<h1 class="ava-headline ava-wide">This account doesn\'t have access.</h1></div>',
            unsafe_allow_html=True,
        )
        # Escaped: the message contains the email the visitor signed in with.
        st.markdown(f"<p class='ava-lede'>{html.escape(message, quote=False)}</p>", unsafe_allow_html=True)
        st.button("Use a different account", key="switch_account", on_click=st.logout)
        st.markdown(
            '<p class="ava-note">You\'ll be signed out and can choose another Google account.</p>',
            unsafe_allow_html=True,
        )
