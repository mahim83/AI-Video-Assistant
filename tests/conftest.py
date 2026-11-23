import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

LIMIT_VARS = [
    "MAX_VIDEO_MINUTES", "MAX_UPLOAD_MB", "VIDEOS_PER_DAY", "AUDIO_MINUTES_PER_DAY",
    "QUESTIONS_PER_DAY", "QUESTIONS_PER_MINUTE", "MAX_QUESTION_CHARS",
    "MAX_CONCURRENT_JOBS", "ANSWER_MAX_TOKENS", "MIN_FREE_DISK_GB", "ENABLE_YOUTUBE", "SIGNUP_MODE", "SMTP_USER", "SMTP_PASSWORD", "NOTIFY_EMAILS", "APP_URL", "DOMAIN", "ALLOWED_VIDEO_HOSTS", "ENABLE_WHISPER",
]


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Each test gets its own data folder and a known set of users and limits."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("AUTH_MODE", "oidc")
    monkeypatch.setenv("ADMIN_EMAILS", "owner@example.com")
    monkeypatch.setenv("ALLOWED_EMAILS", "friend@example.com")
    for name in LIMIT_VARS:
        monkeypatch.delenv(name, raising=False)

    from core.settings import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def owner():
    from core.users import authorize
    return authorize("owner@example.com", True)


@pytest.fixture
def friend():
    from core.users import authorize
    return authorize("friend@example.com", True)
