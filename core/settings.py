"""
Deployment settings, read once from the environment (.env locally, env_file in Docker).
Every limit has a default, so only the keys and the user lists need setting.
"""
import os
from dataclasses import dataclass
from functools import lru_cache


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise RuntimeError(f"{name} must be a whole number, got {raw!r}")
    if value < 0:
        raise RuntimeError(f"{name} must not be negative, got {value}")
    return value


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    raise RuntimeError(f"{name} must be true or false, got {raw!r}")


def _set(name: str, default: str = "") -> frozenset:
    return frozenset(
        item.strip().lower() for item in os.getenv(name, default).split(",") if item.strip()
    )


@dataclass(frozen=True)
class Settings:
    data_dir: str
    # "oidc": Google sign-in through st.login. "off": no login, for running on
    # your own computer only; the app refuses it unless bound to localhost.
    auth_mode: str
    # Always admins, and can't be removed from the app, so the owner can't be locked out.
    admin_emails: frozenset
    # Allowed as regular users. Admins can also add users in the app.
    allowed_emails: frozenset

    max_video_minutes: int
    max_upload_mb: int
    videos_per_day: int
    audio_minutes_per_day: int
    questions_per_day: int
    questions_per_minute: int
    max_question_chars: int
    max_concurrent_jobs: int
    answer_max_tokens: int
    # New videos are refused below this much free space in DATA_DIR, so a
    # full disk stops new work instead of corrupting a half-written index.
    min_free_disk_gb: int

    allowed_video_hosts: frozenset
    enable_whisper: bool


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    auth_mode = os.getenv("AUTH_MODE", "oidc").strip().lower()
    if auth_mode not in ("oidc", "off"):
        raise RuntimeError(f"AUTH_MODE must be 'oidc' or 'off', got {auth_mode!r}")

    return Settings(
        data_dir=os.getenv("DATA_DIR", "data").strip() or "data",
        auth_mode=auth_mode,
        admin_emails=_set("ADMIN_EMAILS"),
        allowed_emails=_set("ALLOWED_EMAILS"),
        max_video_minutes=_int("MAX_VIDEO_MINUTES", 90),
        max_upload_mb=_int("MAX_UPLOAD_MB", 200),
        videos_per_day=_int("VIDEOS_PER_DAY", 5),
        audio_minutes_per_day=_int("AUDIO_MINUTES_PER_DAY", 180),
        questions_per_day=_int("QUESTIONS_PER_DAY", 150),
        questions_per_minute=_int("QUESTIONS_PER_MINUTE", 6),
        max_question_chars=_int("MAX_QUESTION_CHARS", 1000),
        max_concurrent_jobs=max(1, _int("MAX_CONCURRENT_JOBS", 2)),
        answer_max_tokens=_int("ANSWER_MAX_TOKENS", 800),
        min_free_disk_gb=_int("MIN_FREE_DISK_GB", 2),
        allowed_video_hosts=_set(
            "ALLOWED_VIDEO_HOSTS",
            "youtube.com,www.youtube.com,m.youtube.com,music.youtube.com,youtu.be",
        ),
        enable_whisper=_bool("ENABLE_WHISPER", True),
    )
