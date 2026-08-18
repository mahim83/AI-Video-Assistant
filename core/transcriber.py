import os
import requests
from pydub import AudioSegment

# Sarvam's sync STT-translate API rejects audio longer than 30s.
# We slice each chunk into 25s pieces (with a 5s safety margin) before sending.
SARVAM_PIECE_SECONDS = 25


# ── Deepgram (default English engine) ────────────────────────────────────────
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
DEEPGRAM_URL = "https://api.deepgram.com/v1/listen"
DEEPGRAM_MODEL = os.getenv("DEEPGRAM_MODEL", "nova-3")


# ── Whisper (local, now opt-in via language="whisper") ───────────────────────
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")


SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
SARVAM_STT_TRANSLATE_URL = "https://api.sarvam.ai/speech-to-text-translate"
SARVAM_MODEL = os.getenv("SARVAM_STT_MODEL", "saaras:v2.5")

_model = None


def load_model():

    global _model  

    if _model is None: 
        # Imported lazily: `import whisper` pulls in torch, which costs seconds
        # of startup. Deepgram is the default now, so most runs never need it.
        import whisper

        print(f"Loading Whisper model: {WHISPER_MODEL} ...")
        _model = whisper.load_model(WHISPER_MODEL) 
        print("Whisper model loaded.")
    return _model 


def transcribe_chunk_whisper(chunk_path: str) -> str:

    model = load_model()  

    result = model.transcribe(chunk_path, task="transcribe")  
    return result["text"]  


def transcribe_chunk_deepgram(chunk_path: str) -> str:
    """
    Send one chunk to Deepgram's pre-recorded API and return the transcript.
    Unlike Sarvam there is no 30s cap, so a full 10-minute chunk goes in one request.
    """
    if not DEEPGRAM_API_KEY:
        raise RuntimeError("DEEPGRAM_API_KEY is not set in environment / .env")

    # Downsample to 16kHz mono before upload. Speech recognition gains nothing
    # from 44.1kHz stereo, and this cuts a 10-minute chunk from ~100MB to ~10MB.
    audio = AudioSegment.from_file(chunk_path).set_channels(1).set_frame_rate(16000)
    small_path = f"{chunk_path}_dg.wav"
    audio.export(small_path, format="wav")

    try:
        with open(small_path, "rb") as f:
            response = requests.post(
                DEEPGRAM_URL,
                headers={
                    "Authorization": f"Token {DEEPGRAM_API_KEY}",
                    "Content-Type": "audio/wav",
                },
                params={
                    "model": DEEPGRAM_MODEL,
                    "smart_format": "true",
                    "punctuate": "true",
                },
                data=f,
                timeout=600,
            )
    finally:
        if os.path.exists(small_path):
            os.remove(small_path)

    if not response.ok:
        print(f"\n❌ Deepgram returned {response.status_code}")
        print(f"Response body: {response.text}\n")
        response.raise_for_status()

    channels = response.json().get("results", {}).get("channels", [])
    if not channels or not channels[0].get("alternatives"):
        return ""
    return channels[0]["alternatives"][0].get("transcript", "")


def _send_to_sarvam(piece_path: str) -> str:
    """Send one ≤30s WAV file to Sarvam and return the English transcript."""
    headers = {"api-subscription-key": SARVAM_API_KEY}

    with open(piece_path, "rb") as f:
        files = {"file": (os.path.basename(piece_path), f, "audio/wav")}
        data = {"model": SARVAM_MODEL, "with_diarization": "false"}
        response = requests.post(
            SARVAM_STT_TRANSLATE_URL,
            headers=headers,
            files=files,
            data=data,
            timeout=120,
        )

    if not response.ok:
        print(f"\n❌ Sarvam returned {response.status_code}")
        print(f"Response body: {response.text}\n")
        response.raise_for_status()

    return response.json().get("transcript", "")


def transcribe_chunk_sarvam(chunk_path: str) -> str:
    """
    Sarvam sync API only accepts ≤30s audio. We split this chunk into
    25-second pieces, send each separately, and join the transcripts.
    """
    if not SARVAM_API_KEY:
        raise RuntimeError("SARVAM_API_KEY is not set in environment / .env")

    audio = AudioSegment.from_wav(chunk_path)
    piece_ms = SARVAM_PIECE_SECONDS * 1000

    full_text = ""
    total_pieces = (len(audio) + piece_ms - 1) // piece_ms

    for i, start in enumerate(range(0, len(audio), piece_ms)):
        piece = audio[start: start + piece_ms]
        piece_path = f"{chunk_path}_sv_{i}.wav"
        piece.export(piece_path, format="wav")

        try:
            print(f"  → Sarvam piece {i + 1}/{total_pieces} ...")
            full_text += _send_to_sarvam(piece_path) + " "
        finally:
            if os.path.exists(piece_path):
                os.remove(piece_path)

    return full_text.strip()


ENGINE_NAMES = {
    "english": "Deepgram",
    "hinglish": "Sarvam AI",
    "whisper": "Whisper (local)",
}


def transcribe_chunk(chunk_path: str, language: str = "english") -> str:
    """
    Route one chunk to the right engine.
    - english  → Deepgram (cloud, fast)
    - hinglish → Sarvam (translates to English while transcribing)
    - whisper  → local Whisper model, kept as an offline fallback
    """
    lang = language.lower()
    if lang == "hinglish":
        return transcribe_chunk_sarvam(chunk_path)
    if lang == "whisper":
        return transcribe_chunk_whisper(chunk_path)
    return transcribe_chunk_deepgram(chunk_path)


def transcribe_all(chunks: list, language: str = "english") -> str:

    full_transcript = "" 

    engine = ENGINE_NAMES.get(language.lower(), "Deepgram")
    print(f"Using {engine} for transcription.")

    for i, chunk in enumerate(chunks):  

        print(f"Transcribing chunk {i + 1}/{len(chunks)}...")

        text = transcribe_chunk(chunk, language=language)  

        full_transcript += text + " "  

    print("Transcription complete.")

    return full_transcript.strip()
