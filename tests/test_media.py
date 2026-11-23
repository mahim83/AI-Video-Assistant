import os
import shutil
import subprocess

import pytest
import yt_dlp

from core.errors import GuardrailError
from utils import audio_processor
from utils.audio_processor import MediaError, convert_to_wav, wav_minutes

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg not installed")


def _tone(path, seconds=3):
    subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi",
         "-i", f"sine=frequency=440:duration={seconds}", path],
        check=True,
    )


@needs_ffmpeg
def test_upload_converts_to_16k_mono(tmp_path):
    src = tmp_path / "upload.mp3"
    _tone(str(src))
    wav = convert_to_wav(str(src), str(tmp_path), input_format="mp3", max_minutes=10)
    assert 0.04 < wav_minutes(wav) < 0.06
    import wave
    with wave.open(wav) as w:
        assert (w.getnchannels(), w.getframerate()) == (1, 16000)


@needs_ffmpeg
def test_non_media_upload_rejected(tmp_path):
    src = tmp_path / "upload.mp4"
    src.write_text("not a video")
    with pytest.raises(MediaError):
        convert_to_wav(str(src), str(tmp_path), input_format="mp4")


@needs_ffmpeg
def test_playlist_disguised_as_mp4_cannot_read_other_files(tmp_path):
    secret = tmp_path / "secret.mp3"
    _tone(str(secret))
    playlist = tmp_path / "upload.mp4"
    playlist.write_text(
        "#EXTM3U\n#EXT-X-TARGETDURATION:10\n#EXTINF:3,\n"
        f"{secret.as_posix()}\n#EXT-X-ENDLIST\n"
    )
    # Forced to the mp4 demuxer, FFmpeg can't follow the playlist to the other file.
    with pytest.raises(MediaError):
        convert_to_wav(str(playlist), str(tmp_path), input_format="mp4")


@needs_ffmpeg
def test_over_long_recording_rejected(tmp_path):
    src = tmp_path / "upload.wav"
    _tone(str(src), seconds=5)
    with pytest.raises(GuardrailError):
        convert_to_wav(str(src), str(tmp_path), input_format="wav", max_minutes=0.05)  # 3 s


def test_only_youtube_extractor_is_loaded():
    with yt_dlp.YoutubeDL(audio_processor._ydl_opts()) as ydl:
        assert list(ydl._ies) == ["Youtube"] or set(ydl._ies) == {"Youtube"}
        # No extractor matches, so yt-dlp refuses without a network request.
        with pytest.raises(yt_dlp.utils.DownloadError):
            ydl.extract_info("http://169.254.169.254/latest/meta-data/", download=False)
