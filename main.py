import sys
# Windows defaults stdout to cp1252, which cannot encode the emoji below
# (or any emoji the LLM returns in its own answers). Force UTF-8 output.
sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv()   # MUST be before any core/ imports — transcriber.py reads
                # os.getenv("SARVAM_API_KEY") at module level, i.e. at import time.

import re
from datetime import datetime

from utils.audio_processor import process_input, wav_minutes
from core.transcriber import transcribe_all
from core.summarizer import summarize, generate_title
from core.rag_engine import build_rag_chain, load_rag_chain, ask_question
from core.errors import GuardrailError
from core import storage
from core.users import LOCAL_USER

# Runs once per process, before any index is opened: finishes deletes a
# previous run found locked and removes audio a crashed job left behind.
storage.cleanup_on_start()


def _slug(text: str) -> str:
    # Chroma collection names: 3-63 chars, must start and end alphanumeric.
    s = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
    return s[:40] or "meeting"


def run_pipeline(source: str, language: str = "english", on_step=None, *,
                 work_dir: str, persist_directory: str, input_format: str = None,
                 max_minutes: float = None, before_transcribe=None) -> dict:
    """
    Process one video. Audio is written only inside work_dir, which the caller
    creates and deletes (storage.job_dir), and the search index goes to
    persist_directory.

    on_step(msg) lets a UI report progress; the CLI just prints.
    before_transcribe(minutes) runs once the audio length is known and before
    the first paid API call; the web app charges the user's quota there.
    """
    def step(msg):
        print(msg)
        if on_step:
            on_step(msg)

    step("starting AI Video Assistant")

    step("Downloading and preparing audio...")
    wav_path, chunks = process_input(source, work_dir, input_format=input_format, max_minutes=max_minutes)
    minutes = wav_minutes(wav_path)
    if before_transcribe:
        before_transcribe(minutes)

    step(f"Transcribing {len(chunks)} chunk(s) with {language}...")
    transcript = transcribe_all(chunks, language)
    if not transcript.strip():
        raise GuardrailError("No speech was found in this recording.")
    # Word count only: transcripts are users' private content and don't belong in logs.
    print(f"Transcribed {len(transcript.split())} words.")

    step("Generating title...")
    title = generate_title(transcript)

    step("Writing summary...")
    summary = summarize(transcript)

    step("Building searchable index...")
    collection_name = f"{_slug(title)}_{datetime.now():%Y%m%d_%H%M%S}"
    rag_chain = build_rag_chain(transcript, collection_name=collection_name,
                                persist_directory=persist_directory)

    return {
        "title": title,
        "transcript": transcript,
        "summary": summary,
        "collection_name": collection_name,
        "audio_minutes": round(minutes, 1),
        "rag_chain": rag_chain,
    }


def print_result(result: dict):
    print("\n" + "=" * 60)
    print(f"📌 Title: {result['title']}")
    print(f"\n📋 Summary:\n{result['summary']}")
    print("=" * 60)


def chat(rag_chain):
    print("\n💬 Chat with your meeting (type 'exit' to quit)\n")
    history = []
    while True:
        question = input("You: ").strip()
        if question.lower() in ["exit", "quit", "q"]:
            print("👋 Goodbye!")
            break
        if not question:
            continue
        answer = ask_question(rag_chain, question, history)
        history += [{"role": "user", "content": question}, {"role": "assistant", "content": answer}]
        print(f"\n🤖 Assistant: {answer}\n")


if __name__ == "__main__":
    # The terminal app runs on your own computer, so it uses the "local"
    # user's folder, the same one the web app uses with AUTH_MODE=off.
    space = storage.user_space(LOCAL_USER.id)
    result = None
    source = None

    saved = storage.list_meetings(space)
    if saved:
        print("\nSaved meetings:")
        for i, name in enumerate(saved, 1):
            print(f"  [{i}] {name[:-5]}")
        print()
        # One prompt, two jobs: a number reopens a saved meeting, anything else
        # is treated as the source. Asking twice made people paste the URL at
        # this prompt and watch it get ignored.
        answer = input("Pick a number to reopen, or paste a YouTube URL / file path: ").strip()

        if answer.isdigit() and 1 <= int(answer) <= len(saved):
            result = storage.load_meeting(space, saved[int(answer) - 1])
            # Reopens stored embeddings or rebuilds a missing index from the transcript.
            result["rag_chain"] = load_rag_chain(result["collection_name"], result["transcript"],
                                                 persist_directory=space.vector_dir)
            print(f"Loaded: {result['title']}")
        elif answer.isdigit():
            print(f"No meeting numbered {answer}. Starting a new one instead.")
        elif answer:
            source = answer

    if result is None:
        # Keep asking rather than dying deep inside FFmpeg on an empty string.
        while not source:
            source = input("Enter YouTube URL or local file path: ").strip()
            if not source:
                print("  Nothing entered — paste a YouTube URL or a path to an audio/video file.")

        language = input("Language [english / hinglish / whisper] (default english): ").strip() or "english"
        with storage.job_dir(space) as work:
            result = run_pipeline(source, language, work_dir=work, persist_directory=space.vector_dir)
        print(f"\n💾 Saved to {storage.save_meeting(space, result, source)}")

    print_result(result)
    chat(result["rag_chain"])
