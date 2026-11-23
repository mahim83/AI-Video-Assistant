import os
import shutil
import subprocess
import wave

import yt_dlp
from pydub import AudioSegment

from core.errors import GuardrailError, UserFacingError


class MediaError(UserFacingError):
    """The input couldn't be read as audio. The message is safe to show."""


# Audio decoders FFmpeg may use on untrusted files. Video and other streams
# are refused outright, so crafted video data never reaches a video decoder;
# the audio track is still extracted.
AUDIO_CODECS = ",".join([
    "aac", "aac_fixed", "mp3", "mp3float", "opus", "libopus", "vorbis", "libvorbis",
    "flac", "alac", "pcm_s16le", "pcm_s24le", "pcm_s32le", "pcm_f32le", "pcm_u8",
    "pcm_s16be", "pcm_mulaw", "pcm_alaw",
])
# Extension of a YouTube download -> FFmpeg demuxer, so downloads are decoded
# with a fixed format too rather than whatever FFmpeg guesses.
DOWNLOAD_FORMATS = {".m4a": "mp4", ".mp4": "mp4", ".webm": "webm", ".mp3": "mp3", ".opus": "ogg", ".ogg": "ogg"}
# Far above a 90-minute audio stream (~100 MB); stops a runaway download.
MAX_DOWNLOAD_BYTES = 400 * 1024 * 1024
FFMPEG_TIMEOUT_SECONDS = 600


def _ydl_opts(out_dir: str = None) -> dict:
    opts = {
        "format": "bestaudio/best",
        "noplaylist": True,
        # Only YouTube's single-video extractor is loaded. yt-dlp would
        # otherwise accept thousands of sites, and its generic extractor will
        # fetch any URL, including internal addresses on the server's network.
        "allowed_extractors": ["youtube"],
        # The "web"/"tv"/"ios"/"mweb" clients now gate their media URLs behind a
        # GVS PO token; without one YouTube serves the manifest but 403s the
        # actual bytes. "android" and "tv_simply" still hand out playable URLs.
        # Do NOT set a custom user_agent here — yt-dlp sends the UA that matches
        # whichever client answered, and overriding it re-triggers the 403.
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "tv_simply"],
            }
        },
        "socket_timeout": 30,
        "retries": 5,
        "max_filesize": MAX_DOWNLOAD_BYTES,
        "http_headers": {
            "Accept-Language": "en-US,en;q=0.9",
        },
        "quiet": True,
        "no_warnings": True,
    }
    if out_dir:
        # The video id, not its title: titles can be long or contain characters
        # that are awkward in paths.
        opts["outtmpl"] = os.path.join(out_dir, "%(id)s.%(ext)s")

    cookie_file = os.getenv("YTDLP_COOKIES", "").strip()
    browser = os.getenv("YTDLP_BROWSER", "").strip().lower()
    if cookie_file:
        cookie_file = os.path.expanduser(cookie_file)
        if not os.path.isfile(cookie_file):
            raise FileNotFoundError("YTDLP_COOKIES does not point to an existing cookie file")
        opts["cookiefile"] = cookie_file
    elif browser:
        opts["cookiesfrombrowser"] = (browser,)
    return opts


def youtube_minutes(url: str) -> float:
    """Length of a YouTube video in minutes, read before anything is downloaded."""
    with yt_dlp.YoutubeDL(_ydl_opts()) as ydl:
        info = ydl.extract_info(url, download=False)
    if info.get("is_live") or info.get("live_status") in ("is_live", "is_upcoming"):
        raise GuardrailError("Live streams and premieres can't be processed. Try again after it ends.")
    duration = info.get("duration")
    if not duration:
        raise GuardrailError("YouTube didn't report this video's length, so it can't be processed.")
    return duration / 60


def download_youtube_audio(url: str, out_dir: str) -> str:
    """Download the best audio stream as is; convert_to_wav() normalises it after."""
    with yt_dlp.YoutubeDL(_ydl_opts(out_dir)) as ydl:
        info = ydl.extract_info(url, download=True)

        for download in info.get("requested_downloads") or []:
            if download.get("filepath"):
                return download["filepath"]
        return ydl.prepare_filename(info)


def convert_to_wav(input_path: str, out_dir: str = None, input_format: str = None,
                   max_minutes: float = None) -> str:
    """
    Decode any audio/video file to 16 kHz mono WAV, the format every engine
    takes, about 1.9 MB per minute.

    input_format forces FFmpeg's demuxer (set for uploads, from the extension),
    and only plain file access is allowed, so a crafted file can't make FFmpeg
    read other files or URLs. max_minutes stops decoding just past the limit,
    so an over-long file is rejected without decoding all of it.
    """
    out_dir = out_dir or os.path.dirname(os.path.abspath(input_path))
    output_path = os.path.join(out_dir, "audio.wav")
    if os.path.abspath(output_path) == os.path.abspath(input_path):
        output_path = os.path.join(out_dir, "audio_converted.wav")

    cmd = [shutil.which("ffmpeg") or "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
           "-y", "-protocol_whitelist", "file"]
    if input_format:
        cmd += ["-format_whitelist", input_format, "-codec_whitelist", AUDIO_CODECS, "-f", input_format]
    cmd += ["-i", input_path, "-vn", "-sn", "-dn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le"]
    if max_minutes:
        cmd += ["-t", str(int(max_minutes * 60) + 1)]
    cmd.append(output_path)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        raise MediaError("Converting the audio took too long. Try a shorter or smaller file.")
    if result.returncode != 0 or not os.path.isfile(output_path):
        print(f"ffmpeg failed ({result.returncode}): {result.stderr.strip()[-500:]}")
        raise MediaError("This file couldn't be read as audio. Check that it's a valid audio or video file.")

    if max_minutes and wav_minutes(output_path) > max_minutes:
        raise GuardrailError(f"Recordings can be at most {max_minutes:g} minutes long.")
    return output_path


def wav_minutes(path: str) -> float:
    with wave.open(path, "rb") as w:
        return w.getnframes() / w.getframerate() / 60



def chunk_audio(wav_path : str , chunk_minutes : int = 10) -> list:
    audio = AudioSegment.from_wav(wav_path)
    chunk_ms = chunk_minutes * 60 * 1000

    chunks = []

    for i, start in enumerate(range(0,len(audio),chunk_ms)):
        chunk = audio[start : start + chunk_ms]
        chunk_path = f"{wav_path}_chunk_{i}.wav"
        chunk.export(chunk_path , format = "wav")

        chunks.append(chunk_path)

    return chunks


def is_url(source: str) -> bool:
    return source.startswith("http://") or source.startswith("https://")


def process_input(source: str, work_dir: str, input_format: str = None,
                  max_minutes: float = None) -> tuple:
    """
    Return (wav_path, chunks): the full WAV and the chunk files cut from it,
    all written in work_dir. The caller deletes work_dir when done.

    max_minutes is checked before a YouTube download and again on the
    decoded audio, so a mislabelled length can't slip through.
    """
    if is_url(source):
        if max_minutes:
            minutes = youtube_minutes(source)
            if minutes > max_minutes:
                raise GuardrailError(
                    f"This video is {minutes:.0f} minutes long; the limit is {max_minutes:g} minutes."
                )
        print("Detected YouTube URL. Downloading audio...")
        source = download_youtube_audio(source, work_dir)
        input_format = DOWNLOAD_FORMATS.get(os.path.splitext(source)[1].lower())
    else:
        print("Detected local file. Converting to WAV...")

    wav_path = convert_to_wav(source, work_dir, input_format=input_format, max_minutes=max_minutes)

    print("Chunking audio...")
    chunks = chunk_audio(wav_path)
    print(f"Audio ready — {len(chunks)} chunk(s) created.")
    return wav_path, chunks
