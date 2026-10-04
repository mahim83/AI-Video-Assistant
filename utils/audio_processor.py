import yt_dlp
from pydub import AudioSegment
import os

DOWNLOAD_DIR = 'downloads'
os.makedirs(DOWNLOAD_DIR,exist_ok = True)

def download_youtube_audio(url :str) ->str:
    output_path = os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_path,
        "noplaylist": True,
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
        "http_headers": {
            "Accept-Language": "en-US,en;q=0.9",
        },
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
                "preferredquality": "192",
            }
        ],
        "quiet": True,
        "no_warnings": True,
    }
    cookie_file = os.getenv("YTDLP_COOKIES", "").strip()
    browser = os.getenv("YTDLP_BROWSER", "").strip().lower()
    if cookie_file:
        cookie_file = os.path.expanduser(cookie_file)
        if not os.path.isfile(cookie_file):
            raise FileNotFoundError("YTDLP_COOKIES does not point to an existing cookie file")
        ydl_opts["cookiefile"] = cookie_file
    elif browser:
        ydl_opts["cookiesfrombrowser"] = (browser,)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

        # FFmpegExtractAudio records the real post-conversion path here.
        # prepare_filename() still reports the pre-postprocessor extension.
        for download in info.get("requested_downloads") or []:
            if download.get("filepath"):
                return download["filepath"]

        return os.path.splitext(ydl.prepare_filename(info))[0] + ".wav"



def convert_to_wav(input_path: str) -> str:
    """Convert any audio/video file to WAV format using pydub."""
    output_path = os.path.splitext(input_path)[0] + "_converted.wav"
    audio = AudioSegment.from_file(input_path)
    audio = audio.set_channels(1).set_frame_rate(16000)
    audio.export(output_path, format="wav")
    return output_path



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


def in_download_dir(path: str) -> bool:
    """
    True for paths inside DOWNLOAD_DIR. Only files there belong to the app; a
    local file passed to the CLI lives elsewhere and must never be deleted.
    """
    root = os.path.normcase(os.path.abspath(DOWNLOAD_DIR))
    return os.path.normcase(os.path.abspath(path)).startswith(root + os.sep)


def process_input(source: str) -> tuple:
    """Return (wav_path, chunks): the full WAV and the chunk files cut from it."""
    if source.startswith("http://") or source.startswith("https://"):
        print("Detected YouTube URL. Downloading audio...")
        wav_path = download_youtube_audio(source)
    else:
        print("Detected local file. Converting to WAV...")
        wav_path = convert_to_wav(source)

    print("Chunking audio...")
    chunks = chunk_audio(wav_path)
    print(f"Audio ready — {len(chunks)} chunk(s) created.")
    return wav_path, chunks