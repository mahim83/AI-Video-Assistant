import sys
# Windows defaults stdout to cp1252, which cannot encode the emoji below
# (or any emoji the LLM returns in its own answers). Force UTF-8 output.
sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv()   # MUST be before any core/ imports — transcriber.py reads
                # os.getenv("SARVAM_API_KEY") at module level, i.e. at import time.

import json
import os
import re
from datetime import datetime

from utils.audio_processor import process_input
from core.transcriber import transcribe_all
from core.summarizer import summarize, generate_title
from core.extractor import extract_action_items, extract_key_decisions, extract_questions
from core.rag_engine import build_rag_chain, load_rag_chain, ask_question

OUTPUT_DIR = "outputs"


def _slug(text: str) -> str:
    # Chroma collection names: 3-63 chars, must start and end alphanumeric.
    s = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
    return s[:40] or "meeting"


def save_result(result: dict, source: str) -> str:
    """Persist everything except the rag_chain, which is a live object."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    payload = {k: v for k, v in result.items() if k != "rag_chain"}
    payload["source"] = source
    payload["saved_at"] = datetime.now().isoformat(timespec="seconds")

    path = os.path.join(OUTPUT_DIR, payload["collection_name"] + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def list_saved() -> list:
    if not os.path.isdir(OUTPUT_DIR):
        return []
    return sorted(f for f in os.listdir(OUTPUT_DIR) if f.endswith(".json"))


def load_saved(filename: str) -> dict:
    with open(os.path.join(OUTPUT_DIR, filename), encoding="utf-8") as f:
        return json.load(f)


def run_pipeline(source: str, language: str = "english", on_step=None) -> dict:
    """on_step(msg) lets a UI report progress; the CLI just prints."""
    def step(msg):
        print(msg)
        if on_step:
            on_step(msg)

    step("starting AI Video Assistant")

    step("Downloading and preparing audio...")
    chunks = process_input(source)

    step(f"Transcribing {len(chunks)} chunk(s) with {language}...")
    transcript = transcribe_all(chunks, language)
    print(f"raw transcription (first 300 characters ) {transcript[:300]}")

    step("Generating title...")
    title = generate_title(transcript)

    step("Writing summary...")
    summary = summarize(transcript)

    step("Extracting action items...")
    action_item = extract_action_items(transcript)

    step("Extracting key decisions...")
    decisions = extract_key_decisions(transcript)

    step("Extracting open questions...")
    questions = extract_questions(transcript)

    step("Building searchable index...")
    collection_name = f"{_slug(title)}_{datetime.now():%Y%m%d_%H%M%S}"
    rag_chain = build_rag_chain(transcript, collection_name=collection_name)

    return {
        "title": title,
        "transcript": transcript,
        "summary": summary,
        "action_items": action_item,
        "key_decisions": decisions,
        "open_questions": questions,
        "collection_name": collection_name,
        "rag_chain": rag_chain,
    }


def print_result(result: dict):
    print("\n" + "=" * 60)
    print(f"📌 Title: {result['title']}")
    print(f"\n📋 Summary:\n{result['summary']}")
    print(f"\n✅ Action Items:\n{result['action_items']}")
    print(f"\n🔑 Key Decisions:\n{result['key_decisions']}")
    print(f"\n❓ Open Questions:\n{result['open_questions']}")
    print("=" * 60)


def chat(rag_chain):
    print("\n💬 Chat with your meeting (type 'exit' to quit)\n")
    while True:
        question = input("You: ").strip()
        if question.lower() in ["exit", "quit", "q"]:
            print("👋 Goodbye!")
            break
        if not question:
            continue
        print(f"\n🤖 Assistant: {ask_question(rag_chain, question)}\n")


if __name__ == "__main__":
    # CLI entry point
    result = None
    source = None

    saved = list_saved()
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
            result = load_saved(saved[int(answer) - 1])
            # Reopens the stored embeddings — no re-download, no re-transcribe.
            result["rag_chain"] = load_rag_chain(result["collection_name"])
            print(f"Loaded: {result['title']}")
        elif answer.isdigit():
            print(f"No meeting numbered {answer}. Starting a new one instead.")
        elif answer:
            source = answer

    if result is None:
        # Keep asking rather than dying deep inside pydub on an empty string.
        while not source:
            source = input("Enter YouTube URL or local file path: ").strip()
            if not source:
                print("  Nothing entered — paste a YouTube URL or a path to an audio/video file.")

        language = input("Language [english / hinglish / whisper] (default english): ").strip() or "english"
        result = run_pipeline(source, language)
        print(f"\n💾 Saved to {save_result(result, source)}")

    print_result(result)
    chat(result["rag_chain"])
