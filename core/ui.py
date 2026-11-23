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

/* Credit: end of the front page and bottom of the sidebar. */
.ava-footer a, .ava-credit a { color: var(--ava-muted); text-decoration: underline; text-underline-offset: 3px; }
.ava-footer a:hover, .ava-credit a:hover { color: var(--ava-accent); }
.ava-gh { display: inline-flex; align-items: center; gap: .35rem; }
.ava-footer .ava-gh, .ava-credit .ava-gh { text-decoration: none; }
.ava-gh span { text-decoration: underline; text-underline-offset: 3px; }
.ava-credit { font-size: .8125rem; line-height: 1.7; color: var(--ava-faint); margin: 1.5rem 0 0 0; }

/* Same-tab link styled as a secondary button (sign-out for email accounts). */
.ava-button-link { display: inline-block; padding: .55rem 1rem; border: 1px solid var(--ava-rule);
                   border-radius: .375rem; background: var(--ava-raised); color: var(--ava-ink) !important;
                   text-decoration: none !important; font-size: .875rem;
                   transition: border-color 150ms ease-out, color 150ms ease-out; }
.ava-button-link.ava-block { display: block; text-align: center; }
.ava-button-link:hover { border-color: var(--ava-accent); color: var(--ava-accent) !important; }
.ava-button-link:focus-visible { outline: 2px solid var(--ava-accent); outline-offset: 2px; }
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
.ava-note a { color: var(--ava-accent); font-weight: 600; text-decoration: underline;
              text-underline-offset: 3px; }
.ava-note a:hover { color: var(--ava-accent-strong); }
.ava-note a:focus-visible { outline: 2px solid var(--ava-accent); outline-offset: 2px; border-radius: 2px; }
.st-key-signedout [data-testid="stForm"], .st-key-signin_box [data-testid="stForm"] { margin-top: .5rem; max-width: 26rem; }

/* Sign in | Sign up: two links styled as tabs. */
.ava-authtabs { display: flex; gap: 1.75rem; border-bottom: 1px solid var(--ava-rule);
                margin: 0 0 1.25rem 0; max-width: 26rem; }
.ava-authtabs a { padding: .55rem 0; margin-bottom: -1px; font-size: 1rem; font-weight: 600;
                  color: var(--ava-muted); text-decoration: none; border-bottom: 2px solid transparent;
                  transition: color 150ms ease-out, border-color 150ms ease-out; }
.ava-authtabs a:hover { color: var(--ava-ink); }
.ava-authtabs a.ava-on { color: var(--ava-accent); border-bottom-color: var(--ava-accent); }
.ava-authtabs a:focus-visible { outline: 2px solid var(--ava-accent); outline-offset: 3px; border-radius: 2px; }

/* Top bar: brand on the left, Sign in and Sign up on the right.
   Starts below Streamlit's own toolbar so its menu never covers the buttons. */
.ava-topbar { display: flex; align-items: center; justify-content: space-between; gap: 1rem;
              margin: 1.5rem 0 3rem 0; padding-bottom: 1.25rem; border-bottom: 1px solid var(--ava-rule); }
.ava-topnav { display: flex; align-items: center; gap: .5rem; }
[data-testid="stMarkdownContainer"] .ava-topnav a {
  display: inline-flex; align-items: center; min-height: 2.5rem; padding: 0 1rem;
  border-radius: .375rem; border: 1px solid transparent; font-size: .9375rem; font-weight: 600;
  text-decoration: none; transition: background-color 150ms ease-out, border-color 150ms ease-out, color 150ms ease-out;
}
[data-testid="stMarkdownContainer"] .ava-topnav a.ava-top-in { color: var(--ava-ink); border-color: var(--ava-rule);
                                                              background: var(--ava-raised); }
[data-testid="stMarkdownContainer"] .ava-topnav a.ava-top-in:hover { color: var(--ava-accent); border-color: var(--ava-accent); }
[data-testid="stMarkdownContainer"] .ava-topnav a.ava-top-up { color: #fff; background: var(--ava-accent);
                                                              border-color: var(--ava-accent); }
[data-testid="stMarkdownContainer"] .ava-topnav a.ava-top-up:hover { background: var(--ava-accent-strong);
                                                                    border-color: var(--ava-accent-strong); }
[data-testid="stMarkdownContainer"] .ava-topnav a:focus-visible { outline: 2px solid var(--ava-accent); outline-offset: 2px; }
.ava-signedout.ava-under-bar { padding-top: 0; }

/* "or sign in with email": a quiet rule with the words in the middle. */
.ava-or { display: flex; align-items: center; gap: .75rem; margin: 1.5rem 0 .25rem 0; max-width: 26rem;
          color: var(--ava-faint); font-size: .8125rem; }
.ava-or::before, .ava-or::after { content: ""; flex: 1; height: 1px; background: var(--ava-rule); }

.st-key-signedout .ava-button-link { margin-top: .75rem; }

/* Primary actions on the signed-out pages. */
:is(.st-key-google_signin, .st-key-google_register, .st-key-switch_account, .st-key-request_access, .st-key-request_check, .st-key-register_submit, .st-key-login_submit, .st-key-er_submit, .st-key-verify_submit, .st-key-reset_submit, .st-key-reset_start_submit) button {
  width: auto; min-width: 16rem; min-height: 3rem; padding: 0 1.25rem;
  background: var(--ava-accent); border-color: var(--ava-accent); color: #fff;
}
:is(.st-key-google_signin, .st-key-google_register) button { padding-left: .75rem; }
:is(.st-key-google_signin, .st-key-google_register, .st-key-switch_account, .st-key-request_access, .st-key-request_check, .st-key-register_submit, .st-key-login_submit, .st-key-er_submit, .st-key-verify_submit, .st-key-reset_submit, .st-key-reset_start_submit) button:hover {
  background: var(--ava-accent-strong); border-color: var(--ava-accent-strong); color: #fff;
}
:is(.st-key-google_signin, .st-key-google_register, .st-key-switch_account, .st-key-request_access, .st-key-request_check, .st-key-register_submit, .st-key-login_submit, .st-key-er_submit, .st-key-verify_submit, .st-key-reset_submit, .st-key-reset_start_submit) button:focus-visible {
  outline: 2px solid var(--ava-accent); outline-offset: 3px;
}
:is(.st-key-google_signin, .st-key-google_register, .st-key-switch_account, .st-key-request_access, .st-key-request_check, .st-key-register_submit, .st-key-login_submit, .st-key-er_submit, .st-key-verify_submit, .st-key-reset_submit, .st-key-reset_start_submit) button p {
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

/* Request and no-access pages: one column, one message. */
.st-key-signedout { max-width: 40rem; }

/* The player: what the app does, shown rather than described. A subtitle is
   captioned word by word while the playhead moves along the waveform. */
/* The brand sits in the top bar, so the player's top lines up with the headline. */
.ava-player { margin: .45rem 0 0 0; }
.ava-screen { position: relative; aspect-ratio: 16 / 9; background: var(--ava-ink);
              border-radius: .75rem .75rem 0 0; overflow: hidden; }
.ava-screen .ava-play { position: absolute; left: 50%; top: 42%; width: 3.25rem; height: 3.25rem;
                        transform: translate(-50%, -50%); color: rgba(255,255,255,.22); }
.ava-subtitle { position: absolute; left: 50%; bottom: 1.1rem; transform: translateX(-50%);
                width: max-content; max-width: 88%; margin: 0; text-align: center;
                background: rgba(8, 14, 20, .72); color: #fff; border-radius: .3rem;
                padding: .35rem .75rem; font-size: 1.0625rem; line-height: 1.45; font-weight: 500; }
.ava-scrub { position: relative; height: 3.5rem; background: var(--ava-raised);
             border: 1px solid #E3E8ED; border-top: 0; border-radius: 0 0 .75rem .75rem;
             padding: .75rem 1rem; }
.ava-track { position: absolute; inset: .75rem 1rem; }
.ava-wave { position: absolute; inset: 0; }
.ava-wave svg { display: block; width: 100%; height: 100%; }
.ava-wave rect { fill: #CBD3DC; }
.ava-wave.ava-played rect { fill: var(--ava-accent); }
.ava-wave.ava-played { clip-path: inset(0 58% 0 0); }
.ava-head { position: absolute; top: -.3rem; bottom: -.3rem; left: 42%;
            width: 2px; margin-left: -1px; background: var(--ava-ink); border-radius: 1px; }
.ava-player figcaption { font-size: .8125rem; color: var(--ava-faint); margin-top: .75rem; }

/* Sections below the fold: type and spacing carry the structure, not boxes. */
.ava-section { margin-top: 4.5rem; padding-top: 2.5rem; border-top: 1px solid var(--ava-rule); }
[data-testid="stMarkdownContainer"] .ava-section h2 { font-size: 1.5rem; font-weight: 600;
    letter-spacing: -.012em; margin: 0 0 1.75rem 0; padding: 0; color: var(--ava-ink); }
[data-testid="stMarkdownContainer"] .ava-section h3 { font-size: 1.0625rem; font-weight: 600;
    margin: 0 0 .35rem 0; padding: 0; color: var(--ava-ink); }
.ava-section p { color: var(--ava-muted); font-size: .975rem; line-height: 1.6; margin: 0; }
.ava-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 2.5rem; }
.ava-grid.ava-two { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 2rem 3rem; }
.ava-icon { width: 1.75rem; height: 1.75rem; color: var(--ava-accent); margin-bottom: .8rem; display: block; }
.ava-footer { margin-top: 4rem; padding: 1.5rem 0 1rem; border-top: 1px solid var(--ava-rule);
              display: flex; flex-wrap: wrap; justify-content: space-between; gap: .75rem 2rem; }
.ava-footer p { font-size: .8125rem; color: var(--ava-faint); margin: 0; }

/* The one orchestrated moment, about a second, once: the subtitle is
   captioned word by word as the playhead moves, and the explanation and the
   sign-in follow. Off for anyone who prefers reduced motion. */
@keyframes ava-rise { from { opacity: 0; transform: translateY(.28em); } to { opacity: 1; transform: none; } }
@keyframes ava-progress { from { clip-path: inset(0 100% 0 0); } to { clip-path: inset(0 58% 0 0); } }
@keyframes ava-playhead { from { left: 0; } }
.ava-caption .ava-w { display: inline-block; animation: ava-rise 200ms ease-out both; }
.ava-caption .ava-w:nth-of-type(2)  { animation-delay: 110ms; }
.ava-caption .ava-w:nth-of-type(3)  { animation-delay: 220ms; }
.ava-caption .ava-w:nth-of-type(4)  { animation-delay: 330ms; }
.ava-caption .ava-w:nth-of-type(5)  { animation-delay: 440ms; }
.ava-caption .ava-w:nth-of-type(6)  { animation-delay: 550ms; }
.ava-caption .ava-w:nth-of-type(7)  { animation-delay: 660ms; }
.ava-caption .ava-w:nth-of-type(8)  { animation-delay: 770ms; }
.ava-caption .ava-w:nth-of-type(9)  { animation-delay: 880ms; }
.ava-caption .ava-w:nth-of-type(10) { animation-delay: 990ms; }
.ava-wave.ava-played { animation: ava-progress 1100ms ease-out both; }
.ava-head { animation: ava-playhead 1100ms ease-out both; }
.ava-follow { animation: ava-rise 240ms ease-out 250ms both; }
.st-key-signin_box { animation: ava-rise 240ms ease-out 400ms both; }
@media (prefers-reduced-motion: reduce) {
  .ava-caption .ava-w, .ava-wave.ava-played, .ava-head, .ava-follow, .st-key-signin_box { animation: none; }
}

@media (max-width: 640px) {
  .ava-signedout { padding-top: .5rem; }
  .ava-signedout .ava-brand { margin-bottom: 2rem; }
  .ava-player { margin-top: 1rem; }
  .ava-topbar { margin: 1rem 0 2rem 0; }
  [data-testid="stMarkdownContainer"] .ava-topnav a { padding: 0 .8rem; }
  .ava-subtitle { font-size: .9375rem; bottom: .7rem; }
  .ava-grid, .ava-grid.ava-two { grid-template-columns: 1fr; gap: 1.75rem; }
  .ava-section { margin-top: 3rem; }
}
</style>
""".replace("__GOOGLE_G__", _GOOGLE_G)


def _caption_words(text: str) -> str:
    """Wrap each word so a line can arrive word by word, like live captions."""
    return " ".join(f'<span class="ava-w">{html.escape(w)}</span>' for w in text.split())


def _waveform(bars: int = 64) -> str:
    """A speech-like waveform: deterministic, so the page looks the same on every load."""
    import math
    gap, width = 2.0, 3.0
    rects = []
    for i in range(bars):
        # Two slow sine envelopes give the bursts and pauses of speech.
        amp = 0.18 + 0.82 * abs(math.sin(i * 0.47 + 0.6) * math.sin(i * 0.13 + 1.1))
        h = max(4.0, amp * 40)
        rects.append(f'<rect x="{i * (width + gap):.1f}" y="{(40 - h) / 2:.1f}" '
                     f'width="{width}" height="{h:.1f}" rx="1.5"/>')
    total = bars * (width + gap) - gap
    return (f'<svg viewBox="0 0 {total:.0f} 40" preserveAspectRatio="none" aria-hidden="true">'
            + "".join(rects) + "</svg>")


# A real line from a processed talk, so the illustration shows true output.
# Two caption lines, broken by hand like real subtitles.
PLAYER_SUBTITLE = ("Why did we need MCP?", "What problem is it solving?")

_PLAY_ICON = ('<svg class="ava-play" viewBox="0 0 48 48" fill="none" stroke="currentColor" '
              'stroke-width="2" aria-hidden="true"><circle cx="24" cy="24" r="22"/>'
              '<path d="M20 16l12 8-12 8z" fill="currentColor" stroke="none"/></svg>')

_ICONS = {
    "upload": '<path d="M12 15V4M7.5 8.5 12 4l4.5 4.5"/><path d="M4 15v3.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V15"/>',
    "read": '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 8h6M9 12h6M9 16h3.5"/>',
    "ask": '<path d="M5 5h14a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1h-7l-4 3.5V16H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z"/>',
}


def _icon(name: str) -> str:
    return (f'<svg class="ava-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
            f"{_ICONS[name]}</svg>")


def base_css():
    st.markdown(BASE_CSS, unsafe_allow_html=True)


def _header(headline: str, lede_html: str, caption: bool = False, wide: bool = False,
            follow: bool = False, brand: bool = True):
    words = _caption_words(headline) if caption else html.escape(headline)
    classes = "ava-headline" + (" ava-caption" if caption else "") + (" ava-wide" if wide else "")
    top = BRAND if brand else ""
    st.markdown(
        f'<div class="ava-signedout{"" if brand else " ava-under-bar"}">{top}<h1 class="{classes}">{words}</h1>'
        f'<p class="ava-lede{" ava-follow" if (caption or follow) else ""}">{lede_html}</p></div>',
        unsafe_allow_html=True,
    )


def _note(text: str, follow: bool = False):
    st.markdown(f'<p class="ava-note{" ava-follow" if follow else ""}">{text}</p>', unsafe_allow_html=True)


def _player() -> str:
    wave = _waveform()
    return (
        '<figure class="ava-player">'
        f'<div class="ava-screen" role="img" aria-label="A video playing with live captions">{_PLAY_ICON}'
        f'<p class="ava-subtitle ava-caption">{"<br>".join(_caption_words(l) for l in PLAYER_SUBTITLE)}</p></div>'
        '<div class="ava-scrub"><div class="ava-track">'
        f'<div class="ava-wave">{wave}</div><div class="ava-wave ava-played">{wave}</div>'
        '<div class="ava-head"></div></div></div>'
        "<figcaption>A caption from a 50-minute talk processed with this app.</figcaption>"
        "</figure>"
    )


# Who made the app, shown at the end of the front page and in the sidebar.
AUTHOR_NAME = "Mahim Katiyar"
AUTHOR_URL = "https://github.com/mahim83"
CREDIT = f'<a href="{AUTHOR_URL}" target="_blank" rel="noopener noreferrer">{AUTHOR_NAME}</a>'

_GITHUB_MARK = ('<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="currentColor">'
                '<path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49'
                '-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82'
                '.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15'
                '-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 '
                '2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73'
                '.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>')


def _github_link() -> str:
    return (f'<a class="ava-gh" href="{AUTHOR_URL}" target="_blank" rel="noopener noreferrer">'
            f'{_GITHUB_MARK}<span>github.com/mahim83</span></a>')


def credit_line() -> str:
    """For the signed-in sidebar."""
    return f'<p class="ava-credit">Made by {CREDIT}<br>{_github_link()}</p>'


def _landing_sections(settings) -> str:
    formats = "mp3, mp4, m4a, wav, webm, mkv or aac"
    steps = [
        ("upload", "1. Upload",
         f"Add an audio or video file of a meeting, lecture or talk ({formats}), "
         f"up to {settings.max_video_minutes} minutes and {settings.max_upload_mb} MB."),
        ("read", "2. Read",
         "Get the full transcript and a short summary in bullet points, usually within a few minutes."),
        ("ask", "3. Ask",
         "Ask questions in plain language. Answers come from what was said, and follow-up "
         "questions keep the conversation's context."),
    ]
    uses = [
        ("Lectures and classes", "Find where a concept was explained without rewatching the whole class."),
        ("Team meetings", "Check what was decided and what happens next, with the transcript to back it up."),
        ("Interviews and podcasts", "Pull the main points and exact quotes out of long conversations."),
        ("Hindi-English talks", "Hinglish recordings are transcribed and translated into English."),
    ]
    youtube = ("Paste a YouTube link, or upload the file." if settings.enable_youtube else
               "Not on this server: YouTube blocks downloads from cloud servers. "
               "Save the video's audio as a file and upload it instead.")
    faq = [
        ("Who can see my meetings?",
         "Not other users. Each account has its own private space, so nobody else using the app can "
         "see or search your meetings."),
        ("Does it cost anything?",
         f"Not for approved users. Each account can process {settings.videos_per_day} recordings "
         f"and {settings.audio_minutes_per_day} minutes of audio, and ask {settings.questions_per_day} "
         "questions a day. Limits reset at 00:00 UTC."),
        ("Which languages work?",
         "English, and Hindi-English (Hinglish), which is translated into English."),
        ("What happens to my recording?",
         "The audio goes to Deepgram or Sarvam for transcription and is deleted from this server as "
         "soon as the transcript is ready. Summaries and answers are written by OpenAI."),
        ("Can I use YouTube links?", youtube),
        ("How do I get access?",
         "Use Sign up at the top of this page, with Google or your email. The admin approves new accounts."
         if settings.signup_mode == "request" else
         "Ask the person who runs this app to add your Google account, then sign in."),
    ]
    step_html = "".join(f'<div>{_icon(i)}<h3>{t}</h3><p>{d}</p></div>' for i, t, d in steps)
    use_html = "".join(f"<div><h3>{t}</h3><p>{d}</p></div>" for t, d in uses)
    faq_html = "".join(f"<div><h3>{q}</h3><p>{a}</p></div>" for q, a in faq)
    return (
        f'<section class="ava-section"><h2>How it works</h2><div class="ava-grid">{step_html}</div></section>'
        f'<section class="ava-section"><h2>Good for</h2><div class="ava-grid ava-two">{use_html}</div></section>'
        f'<section class="ava-section"><h2>Good to know</h2><div class="ava-grid ava-two">{faq_html}</div></section>'
        f'<footer class="ava-footer"><p>AI Video Assistant, made by {CREDIT}</p>'
        f'<p>{_github_link()}</p></footer>'
    )


# Signed-out pages have their own addresses, so they can be linked and shared.
REGISTER_HREF = "?page=register"
RESET_HREF = "?page=reset"
HOME_HREF = "?"


def _link(href: str, text: str) -> str:
    return f'<a href="{href}" target="_self">{text}</a>'


def _or(text: str):
    st.markdown(f'<div class="ava-or"><span>{text}</span></div>', unsafe_allow_html=True)


def _go_to(url: str):
    """Send the browser to url (the cookie-setting route), with a link if it doesn't move."""
    safe = html.escape(url)
    st.markdown(f'<meta http-equiv="refresh" content="0; url={safe}">'
                f'<p class="ava-note">Signing you in. If nothing happens, '
                f'<a href="{safe}" target="_self">continue</a>.</p>', unsafe_allow_html=True)
    st.stop()


def _complete_sign_in(token: str):
    _go_to(f"/local-auth/complete?token={token}")


def _signout_control(signout_href, key: str, label: str = "Use a different account"):
    """Google accounts sign out through st.logout; email accounts through a route that clears the cookie."""
    if signout_href:
        st.markdown(f'<a class="ava-button-link" href="{signout_href}" target="_self">{label}</a>',
                    unsafe_allow_html=True)
    else:
        st.button(label, key=key, on_click=st.logout)


def _email_sign_in_form():
    from core import local_auth
    with st.form("login_form", border=False):
        email = st.text_input("Email", key="login_email", max_chars=254, autocomplete="email")
        password = st.text_input("Password", type="password", key="login_password", max_chars=128,
                                 autocomplete="current-password")
        submitted = st.form_submit_button("Sign in", key="login_submit", type="primary")
    if submitted:
        try:
            _complete_sign_in(local_auth.sign_in(email, password))
        except local_auth.AuthError as e:
            st.error(str(e))
    _note(_link(RESET_HREF, "Forgot your password?"))


def _top_bar(active: str, signup: bool):
    """The brand on the left, Sign in and Sign up on the right, on every signed-out page."""
    def item(key, label, href, cls):
        current = ' aria-current="page"' if key == active else ""
        return f'<a class="{cls}" href="{href}" target="_self"{current}>{label}</a>'
    links = item("signin", "Sign in", HOME_HREF, "ava-top-in")
    if signup:
        links += item("signup", "Sign up", REGISTER_HREF, "ava-top-up")
    st.markdown(f'<header class="ava-topbar">{BRAND}<nav class="ava-topnav" aria-label="Account">'
                f"{links}</nav></header>", unsafe_allow_html=True)


def _auth_tabs(active: str):
    """Sign in | Sign up. Links, not st.tabs, so each has its own address and
    the "Don't have an account? Sign up" line can switch to the other."""
    def tab(key, label, href):
        on = key == active
        current = ' aria-current="page"' if on else ""
        return f'<a class="{"ava-on" if on else ""}" href="{href}" target="_self"{current}>{label}</a>'
    st.markdown(f'<nav class="ava-authtabs" aria-label="Account">{tab("signin", "Sign in", HOME_HREF)}'
                f'{tab("signup", "Sign up", REGISTER_HREF)}</nav>', unsafe_allow_html=True)


def _signin_panel(settings, email_ok: bool):
    st.button("Sign in with Google", key="google_signin", on_click=st.login)
    # Email accounts need email (codes for sign-up and resets), so without
    # SMTP settings only Google is offered.
    if email_ok:
        _or("or sign in with email")
        _email_sign_in_form()
    if settings.signup_mode == "request":
        _note(f"Don't have an account? {_link(REGISTER_HREF, 'Sign up')}")
    else:
        _note("Accounts are by invitation.")


def _signup_panel(settings, email_ok: bool):
    from core import local_auth
    from core.users import NAME_MAX, REASON_MAX
    if settings.signup_mode != "request":
        st.markdown('<p class="ava-tab-lede">Accounts are by invitation. Ask the person who runs '
                    "this app to add your account, then sign in.</p>", unsafe_allow_html=True)
        _note(f"Already registered? {_link(HOME_HREF, 'Sign in')}")
        return

    # Step two of the email path: the code that proves the address is theirs.
    if pending := st.session_state.get("_verify_email"):
        who = html.escape(pending, quote=False)
        st.markdown(f'<p class="ava-tab-lede"><strong>Check your email.</strong> We sent a 6-digit code '
                    f"to {who}. Enter it to finish creating your account. It expires in 15 minutes.</p>",
                    unsafe_allow_html=True)
        with st.form("verify_form", border=False):
            code = st.text_input("6-digit code", key="verify_code", max_chars=6)
            verified = st.form_submit_button("Verify email", key="verify_submit", type="primary")
        if verified:
            try:
                token = local_auth.finish_registration(pending, code)
                st.session_state.pop("_verify_email", None)
                _complete_sign_in(token)
            except local_auth.AuthError as e:
                st.error(str(e))
        c1, c2 = st.columns(2)
        if c1.button("Send a new code", key="verify_resend"):
            try:
                local_auth._send_code(pending, "register")
                st.success("A new code is on its way.")
            except local_auth.AuthError as e:
                st.error(str(e))
        if c2.button("Use a different email", key="verify_restart"):
            st.session_state.pop("_verify_email", None)
            st.rerun()
        return

    last = ("You'll get an email as soon as you're approved."
            if email_ok else "Sign in again once you're approved.")
    st.markdown(f'<p class="ava-tab-lede">New accounts are approved by the admin before they can be '
                f"used. {last}</p>", unsafe_allow_html=True)
    st.button("Sign up with Google", key="google_register", on_click=st.login)

    if email_ok:
        _or("or sign up with email")
        with st.form("email_register_form", border=False):
            name = st.text_input("Full name", key="er_name", max_chars=NAME_MAX, autocomplete="name")
            email = st.text_input("Email", key="er_email", max_chars=254, autocomplete="email")
            password = st.text_input("Password", type="password", key="er_password", max_chars=128,
                                     autocomplete="new-password",
                                     help=f"At least {local_auth.PASSWORD_MIN} characters. "
                                          "A short phrase of several words works well.")
            confirm = st.text_input("Confirm password", type="password", key="er_confirm", max_chars=128,
                                    autocomplete="new-password")
            reason = st.text_area("How will you use AI Video Assistant? (optional)", key="er_reason",
                                  max_chars=REASON_MAX, height=90,
                                  placeholder="For example: summarising my college lectures")
            agree = st.checkbox("I understand that my recordings are transcribed by Deepgram or Sarvam "
                                "and summarised by OpenAI.", key="er_agree")
            created = st.form_submit_button("Create account", key="er_submit", type="primary")
        if created:
            if password != confirm:
                st.error("The two passwords don't match.")
            elif not agree:
                st.error("Tick the box to confirm you understand how recordings are processed.")
            else:
                try:
                    st.session_state["_verify_email"] = local_auth.start_registration(
                        name, email, password, reason)
                    st.rerun()
                except local_auth.AuthError as e:
                    st.error(str(e))
    _note(f"Already registered? {_link(HOME_HREF, 'Sign in')}")


def sign_in_page(active: str = "signin"):
    """The front page: what the app does, and the Sign in | Sign up box."""
    from core import notify
    from core.settings import get_settings
    settings = get_settings()
    email_ok = notify.enabled()
    how = ("Paste a YouTube link or upload a recording." if settings.enable_youtube
           else "Upload a recording of a meeting, lecture or video.")
    st.markdown(SIGNED_OUT_CSS, unsafe_allow_html=True)
    _top_bar(active, settings.signup_mode == "request")
    left, right = st.columns([11, 10], gap="large")
    with right:
        st.markdown(_player(), unsafe_allow_html=True)
    with left:
        _header("Ask questions about any video or meeting recording.",
                f"{how} You get the full transcript, a short summary, "
                "and answers drawn from what was actually said.", caption=False, follow=True,
                brand=False)
        with st.container(key="signin_box"):
            _auth_tabs(active)
            if active == "signup":
                _signup_panel(settings, email_ok)
            else:
                _signin_panel(settings, email_ok)
            _note("Your meetings are private: other users can't see them.")

    st.markdown(_landing_sections(settings), unsafe_allow_html=True)


def register_page():
    """The front page with the Sign up tab open (?page=register)."""
    sign_in_page("signup")


def reset_page():
    """Forgot password: a code by email, then a new password."""
    from core import local_auth
    from core.settings import get_settings
    st.markdown(SIGNED_OUT_CSS, unsafe_allow_html=True)
    _top_bar("reset", get_settings().signup_mode == "request")
    with st.container(key="signedout"):
        if email := st.session_state.get("_reset_email"):
            who = html.escape(email, quote=False)
            _header("Choose a new password.", f"If {who} has an account, we sent it a 6-digit code. "
                    "Enter it with your new password.", wide=True, brand=False)
            with st.form("reset_form", border=False):
                code = st.text_input("6-digit code", key="reset_code", max_chars=6)
                password = st.text_input("New password", type="password", key="reset_password",
                                         max_chars=128, autocomplete="new-password",
                                         help=f"At least {local_auth.PASSWORD_MIN} characters.")
                confirm = st.text_input("Confirm new password", type="password", key="reset_confirm",
                                        max_chars=128, autocomplete="new-password")
                done = st.form_submit_button("Set new password", key="reset_submit", type="primary")
            if done:
                if password != confirm:
                    st.error("The two passwords don't match.")
                else:
                    try:
                        token = local_auth.finish_reset(email, code, password)
                        st.session_state.pop("_reset_email", None)
                        _complete_sign_in(token)
                    except local_auth.AuthError as e:
                        st.error(str(e))
            if st.button("Use a different email", key="reset_restart"):
                st.session_state.pop("_reset_email", None)
                st.rerun()
            return

        _header("Reset your password.", "Enter the email you registered with. We'll send you a code "
                "to choose a new password.", wide=True, brand=False)
        with st.form("reset_start_form", border=False):
            email = st.text_input("Email", key="reset_email_input", max_chars=254, autocomplete="email")
            sent = st.form_submit_button("Send reset code", key="reset_start_submit", type="primary")
        if sent:
            try:
                st.session_state["_reset_email"] = local_auth.start_reset(email)
                st.rerun()
            except local_auth.AuthError as e:
                st.error(str(e))
        _note(f"Signed in with Google? Google manages that password. {_link(HOME_HREF, 'Back to sign in')}.")


def request_page(email: str, status, on_submit, default_name: str = "", error: str = None,
                 signout_href: str = None):
    """
    For a verified account that isn't on the list yet: the registration form
    (Google accounts), or "waiting for approval". on_submit(name, reason)
    records the registration.
    """
    from core import notify
    from core.users import NAME_MAX, REASON_MAX
    who = html.escape(email, quote=False)
    st.markdown(SIGNED_OUT_CSS, unsafe_allow_html=True)
    with st.container(key="signedout"):
        if status == "pending":
            then = (f"You'll get an email at {who} as soon as it's approved."
                    if notify.enabled() else "You can use the app as soon as it's approved.")
            _header("Registration received.",
                    f"Your account for {who} is waiting for the admin's approval. {then}", wide=True)
            st.button("Check again", key="request_check")
        else:
            _header("Complete your registration.",
                    f"You're signed in as {who}. Tell the admin who you are, "
                    "then submit your registration.", wide=True)
            with st.form("register_form", border=False):
                name = st.text_input("Full name", value=default_name or "", max_chars=NAME_MAX, key="reg_name")
                reason = st.text_area("How will you use AI Video Assistant? (optional)", max_chars=REASON_MAX,
                                      key="reg_reason", height=90,
                                      placeholder="For example: summarising my college lectures")
                agree = st.checkbox("I understand that my recordings are transcribed by Deepgram or Sarvam "
                                    "and summarised by OpenAI.", key="reg_agree")
                submitted = st.form_submit_button("Submit registration", key="register_submit", type="primary")
            if submitted:
                if not name.strip():
                    st.error("Enter your name.")
                elif not agree:
                    st.error("Tick the box to confirm you understand how recordings are processed.")
                else:
                    on_submit(name, reason)
                    st.rerun()
        if error:
            st.error(error)
        _signout_control(signout_href, key="switch_account_plain")


def denied_page(message: str, signout_href: str = None):
    st.markdown(SIGNED_OUT_CSS, unsafe_allow_html=True)
    with st.container(key="signedout"):
        # Escaped: the message contains the email the visitor signed in with.
        _header("This account doesn't have access.", html.escape(message, quote=False), wide=True)
        _signout_control(signout_href, key="switch_account")
        _note("You'll be signed out and can choose another account.")

