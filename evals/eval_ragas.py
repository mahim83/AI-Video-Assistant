"""
Answer evaluation with RAGAS: are the chat's answers grounded and on point?

Runs in its own venv, because ragas conflicts with the app's packages:

    python -m venv .venv-eval
    .venv-eval\\Scripts\\python -m pip install -r requirements-eval.txt

    python -m evals.eval_ragas references <meeting.json> [--dataset evals/dataset.json]
    python -m evals.eval_ragas run        <meeting.json> [--dataset ...] [--limit N]

`references` adds a short reference answer to every dataset item that lacks
one, written by the judge model from the passage that holds the evidence
sentence. Review them like the questions: two metrics are scored against them.

`run` answers each question the way the app does (hybrid_retriever, then the
app's rules and model) and has a judge model score:

    faithfulness       every claim in the answer is supported by the 4 chunks
    answer_relevancy   the answer addresses the question
    context_precision  the chunks that help are ranked above those that don't
    context_recall     the 4 chunks contain everything the reference says

Per-question answers and scores go next to the dataset (evals/dataset.json ->
evals/dataset_ragas.json), so a low mean can be traced to the questions behind it.
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

import os
# ragas sends anonymous usage events unless this is set before it is imported.
os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")

from dotenv import load_dotenv
load_dotenv()

import argparse
import asyncio
import json

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from openai import AsyncOpenAI
from ragas.embeddings.base import embedding_factory
from ragas.llms import llm_factory
from ragas.metrics.collections import AnswerRelevancy, ContextPrecision, ContextRecall, Faithfulness

from core.rag_engine import SYSTEM_PROMPT, format_docs, get_llm
from core.retriever import hybrid_retriever
from core.vector_store import EMBEDDING_MODEL, get_embeddings
from evals.eval_retrieval import DATASET, _chunk, _load_transcript, _norm

# A different, stronger model than the one answering: a judge tends to rate
# its own output generously.
JUDGE = os.getenv("RAGAS_JUDGE_MODEL", "gpt-4o")
CONCURRENCY = 4  # judge calls in flight at once; raise it if your rate limit allows

# The sample fields each metric's ascore() takes.
FIELDS = {
    "faithfulness": ("user_input", "response", "retrieved_contexts"),
    "answer_relevancy": ("user_input", "response"),
    "context_precision": ("user_input", "reference", "retrieved_contexts"),
    "context_recall": ("user_input", "retrieved_contexts", "reference"),
}


def references(meeting: str, dataset_path: str, judge: str):
    with open(dataset_path, encoding="utf-8") as f:
        data = json.load(f)
    chunks = _chunk(_load_transcript(meeting))
    llm = ChatOpenAI(model=judge, temperature=0)

    added = 0
    for item in data["items"]:
        if item.get("reference"):
            continue
        evidence = _norm(item["evidence"])
        # Evidence that straddles a chunk boundary is in no chunk; use it alone.
        passage = next((c for c in chunks if evidence in _norm(c)), item["evidence"])
        prompt = (
            "Answer the question using only the passage below, in one or two "
            "sentences. Reply with the answer only.\n\n"
            f"Question: {item['question']}\n\nPassage:\n{passage}"
        )
        item["reference"] = llm.invoke(prompt).content.strip()
        added += 1

    with open(dataset_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Added {added} reference answers to {dataset_path}. Review them before running.")


def _answerer(chunks: list):
    """The app's retrieval and prompt, returning the chunks along with the answer."""
    docs = [Document(page_content=c, metadata={"chunk_index": i}) for i, c in enumerate(chunks)]
    # No persist_directory: the index lives in memory and leaves vector_db/ alone.
    store = Chroma.from_documents(docs, get_embeddings(), collection_name="eval_ragas")
    retrieve = hybrid_retriever(store)
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", "{question}"),
    ])
    generate = prompt | get_llm() | StrOutputParser()

    def answer(question: str):
        found = retrieve.invoke(question)
        response = generate.invoke({"context": format_docs(found), "question": question})
        return response, [d.page_content for d in found]

    return answer


async def _score(rows: list, judge: str):
    llm = llm_factory(judge, client=AsyncOpenAI())
    # The app's local embedding model, so answer relevancy needs no extra API.
    embeddings = embedding_factory("huggingface", f"sentence-transformers/{EMBEDDING_MODEL}", interface="modern")
    metrics = {
        "faithfulness": Faithfulness(llm=llm),
        "answer_relevancy": AnswerRelevancy(llm=llm, embeddings=embeddings),
        "context_precision": ContextPrecision(llm=llm),
        "context_recall": ContextRecall(llm=llm),
    }
    gate = asyncio.Semaphore(CONCURRENCY)

    async def one(row, name, metric):
        async with gate:
            try:
                result = await metric.ascore(**{f: row[f] for f in FIELDS[name]})
                row["scores"][name] = result.value
            except Exception as e:
                # One failed judge call costs one score, not the whole run.
                row["scores"][name] = None
                row.setdefault("errors", {})[name] = f"{type(e).__name__}: {e}"

    await asyncio.gather(*(one(r, n, m) for r in rows for n, m in metrics.items()))


def run(meeting: str, dataset_path: str, judge: str, limit: int = None):
    with open(dataset_path, encoding="utf-8") as f:
        items = json.load(f)["items"][:limit]
    missing = sum(not item.get("reference") for item in items)
    if missing:
        sys.exit(f"{missing} question(s) have no reference answer. Run `references` first.")
    if judge == os.getenv("OPENAI_MODEL", "gpt-4o-mini"):
        print(f"⚠️ The judge ({judge}) also writes the answers, so expect generous scores.")

    answer = _answerer(_chunk(_load_transcript(meeting)))
    rows = []
    for n, item in enumerate(items, 1):
        print(f"Answering {n}/{len(items)} ...")
        response, contexts = answer(item["question"])
        rows.append({
            "user_input": item["question"],
            "reference": item["reference"],
            "response": response,
            "retrieved_contexts": contexts,
            "scores": {},
        })

    print(f"Scoring with {judge} ...")
    asyncio.run(_score(rows, judge))

    # Named after the dataset, so each meeting's results sit beside its questions.
    results = os.path.splitext(dataset_path)[0] + "_ragas.json"
    with open(results, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)

    print(f"\n{len(rows)} questions, judge {judge}\n")
    print(f"{'metric':<20}{'mean':>6}{'scored':>9}")
    for name in FIELDS:
        values = [r["scores"][name] for r in rows if r["scores"].get(name) is not None]
        mean = f"{sum(values) / len(values):.2f}" if values else "-"
        print(f"{name:<20}{mean:>6}{len(values):>6}/{len(rows)}")
    failed = sum(bool(r.get("errors")) for r in rows)
    if failed:
        print(f"\n{failed} question(s) had judge errors; see \"errors\" in {results}.")
    print(f"\nPer-question answers and scores: {results}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["references", "run"])
    p.add_argument("meeting", help="path to a saved meeting JSON in outputs/")
    p.add_argument("--dataset", default=DATASET)
    p.add_argument("--judge", default=JUDGE, help="OpenAI model that scores (default: %(default)s)")
    p.add_argument("--limit", type=int, help="score only the first N questions, for a cheap trial run")
    a = p.parse_args()
    if a.command == "references":
        references(a.meeting, a.dataset, a.judge)
    else:
        run(a.meeting, a.dataset, a.judge, a.limit)
