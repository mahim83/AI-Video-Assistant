"""
Pre-flight check. Run this before `streamlit run app.py` to confirm every
key, service and binary the pipeline needs is actually working.

    python check_setup.py
"""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import os
import shutil
import subprocess

from dotenv import load_dotenv
load_dotenv()   # before any core/ import — transcriber reads keys at import time

results = []


def check(name, fn):
    try:
        ok, detail = fn()
    except Exception as e:
        ok, detail = False, f"{type(e).__name__}: {str(e)[:90]}"
    results.append((ok, name, detail))
    print(f"  {'✅' if ok else '❌'}  {name:<28} {detail}")


print("\nEnvironment")
for key, needed_for in [
    ("DEEPGRAM_API_KEY", "English transcription"),
    ("SARVAM_API_KEY",   "Hinglish transcription"),
    ("OPENAI_API_KEY",   "summary / chat"),
]:
    check(key, lambda k=key, n=needed_for: (
        bool(os.getenv(k)), f"set ({n})" if os.getenv(k) else f"MISSING — {n} will fail"
    ))


print("\nBinaries")

def _ffmpeg():
    path = shutil.which("ffmpeg")
    if not path:
        return False, "not on PATH — pydub/yt-dlp conversion will fail"
    ver = subprocess.run([path, "-version"], capture_output=True, text=True).stdout.split("\n")[0]
    return True, ver[:60]

check("ffmpeg", _ffmpeg)

def _ytdlp():
    import yt_dlp
    return True, f"v{yt_dlp.version.__version__}"

check("yt-dlp", _ytdlp)


print("\nProject imports")

def _main():
    import main  # noqa: F401
    return True, "main.py imports cleanly"


def _app():
    # app.py must be run through Streamlit's harness: imported bare, st.stop()
    # is a no-op and the script keeps going past its own guard.
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file("app.py", default_timeout=180).run()
    if at.exception:
        e = at.exception[0]
        return False, f"{e.type}: {str(e.message)[:70]}"
    return True, "app.py renders with no exceptions"


check("main.py", _main)
check("app.py", _app)


print("\nServices (live calls)")

import requests
from pydub import AudioSegment

SILENCE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_check.wav")


def _deepgram():
    AudioSegment.silent(duration=2000, frame_rate=16000).export(SILENCE, format="wav")
    try:
        with open(SILENCE, "rb") as f:
            r = requests.post(
                "https://api.deepgram.com/v1/listen",
                headers={"Authorization": f"Token {os.getenv('DEEPGRAM_API_KEY')}",
                         "Content-Type": "audio/wav"},
                params={"model": os.getenv("DEEPGRAM_MODEL", "nova-3")},
                data=f, timeout=60,
            )
        return r.ok, f"HTTP {r.status_code} (model={os.getenv('DEEPGRAM_MODEL','nova-3')})"
    finally:
        if os.path.exists(SILENCE):
            os.remove(SILENCE)


def _sarvam():
    AudioSegment.silent(duration=2000, frame_rate=16000).export(SILENCE, format="wav")
    try:
        with open(SILENCE, "rb") as f:
            r = requests.post(
                "https://api.sarvam.ai/speech-to-text-translate",
                headers={"api-subscription-key": os.getenv("SARVAM_API_KEY")},
                files={"file": ("c.wav", f, "audio/wav")},
                data={"model": os.getenv("SARVAM_STT_MODEL", "saaras:v2.5")},
                timeout=60,
            )
        return r.ok, f"HTTP {r.status_code}"
    finally:
        if os.path.exists(SILENCE):
            os.remove(SILENCE)


def _openai():
    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
                 "Content-Type": "application/json"},
        json={"model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
              "messages": [{"role": "user", "content": "ok"}], "max_tokens": 2},
        timeout=60,
    )
    return r.ok, f"HTTP {r.status_code}"


check("Deepgram", _deepgram)
check("Sarvam",   _sarvam)
check("OpenAI",   _openai)


failed = [name for ok, name, _ in results if not ok]
print("\n" + "=" * 58)
if failed:
    print(f"❌ {len(failed)} check(s) failed: {', '.join(failed)}")
    sys.exit(1)
print("✅ All checks passed — run:  streamlit run app.py")
