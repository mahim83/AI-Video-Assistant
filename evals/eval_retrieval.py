"""
Retrieval evaluation: does hybrid search + reranking beat plain vector search?

    python -m evals.eval_retrieval generate <meeting.json> [--n 30]
    python -m evals.eval_retrieval run      <meeting.json> [--dataset evals/dataset.json]

`generate` asks OpenAI to write a question for random transcript passages, plus
the verbatim sentence that answers it. Open evals/dataset.json and delete or fix
weak questions before trusting the numbers.

`run` indexes the transcript in memory and scores three rankers against the
dataset. A retrieved chunk counts as correct if it contains the evidence
sentence, so the score does not depend on where chunk boundaries fall.
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv()

import argparse
import json
import os
import random
import re

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from rank_bm25 import BM25Okapi

from core import retriever
from core.rag_engine import get_llm
from core.vector_store import get_embeddings

DATASET = os.path.join("evals", "dataset.json")
FETCH_K = 20    # candidates taken from each search, as in hybrid_retriever
CUTOFF = 10     # ranks considered for MRR


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _load_transcript(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return json.load(f)["transcript"]


def _chunk(transcript: str) -> list:
    # Same settings as core.vector_store.build_vector_store.
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    return splitter.split_text(transcript)


def generate(meeting: str, n: int, dataset_path: str = DATASET):
    transcript = _load_transcript(meeting)
    chunks = _chunk(transcript)
    random.seed(0)
    sample = random.sample(chunks, min(n, len(chunks)))
    llm = get_llm()
    norm_transcript = _norm(transcript)

    items = []
    for chunk in sample:
        prompt = (
            "Below is a passage from a video transcript. Write ONE question that this "
            "passage answers and that a viewer could ask without seeing the passage. "
            "Do not copy long phrases from the passage; paraphrase where natural. Also "
            "copy, word for word, the single sentence from the passage that answers it.\n"
            'Reply as JSON only: {"question": "...", "evidence": "..."}\n\n'
            f"Passage:\n{chunk}"
        )
        reply = llm.invoke(prompt).content
        try:
            data = json.loads(re.search(r"\{.*\}", reply, re.S).group(0))
            question, evidence = data["question"].strip(), data["evidence"].strip()
        except (AttributeError, KeyError, ValueError):
            continue
        # The model sometimes paraphrases the "verbatim" sentence; drop those.
        if _norm(evidence) not in norm_transcript:
            continue
        items.append({"question": question, "evidence": evidence})

    os.makedirs(os.path.dirname(dataset_path) or ".", exist_ok=True)
    with open(dataset_path, "w", encoding="utf-8") as f:
        json.dump({"meeting": os.path.basename(meeting), "items": items}, f, indent=2, ensure_ascii=False)
    print(f"Wrote {len(items)} questions to {dataset_path}. Review them before running.")


def _rankers(chunks: list):
    docs = [Document(page_content=c, metadata={"chunk_index": i}) for i, c in enumerate(chunks)]
    # No persist_directory: the index lives in memory and leaves vector_db/ alone.
    store = Chroma.from_documents(docs, get_embeddings(), collection_name="eval_tmp")
    corpus = [retriever._tokenize(d.page_content) for d in docs]
    bm25 = BM25Okapi(corpus)
    reranker = retriever.load_reranker()
    n = min(FETCH_K, len(docs))

    def vector(q):
        return store.similarity_search(q, k=CUTOFF)

    def hybrid(q):
        dense = store.similarity_search(q, k=n)
        scores = bm25.get_scores(retriever._tokenize(q))
        top = sorted(range(len(docs)), key=lambda i: scores[i], reverse=True)[:n]
        keyword = [docs[i] for i in top if scores[i] > 0]
        return retriever._fuse([dense, keyword])

    def reranked(q):
        cands = hybrid(q)
        if reranker is None:
            return cands
        rel = reranker.predict([(q, d.page_content) for d in cands])
        return [d for _, d in sorted(zip(rel, cands), key=lambda p: p[0], reverse=True)]

    rankers = {"vector only": vector, "hybrid (vector+BM25)": hybrid}
    if reranker is not None:
        rankers["hybrid + reranker"] = reranked
    else:
        print("Reranker unavailable; skipping that row.")
    return rankers


def run(meeting: str, dataset_path: str):
    with open(dataset_path, encoding="utf-8") as f:
        items = json.load(f)["items"]
    chunks = _chunk(_load_transcript(meeting))
    rankers = _rankers(chunks)

    print(f"\n{len(items)} questions, {len(chunks)} chunks\n")
    print(f"{'ranker':<24}{'hit@1':>8}{'hit@4':>8}{'MRR@10':>9}")
    for name, rank in rankers.items():
        hit1 = hit4 = rr = 0.0
        for item in items:
            evidence = _norm(item["evidence"])
            results = rank(item["question"])[:CUTOFF]
            pos = next((i for i, d in enumerate(results) if evidence in _norm(d.page_content)), None)
            if pos is not None:
                rr += 1 / (pos + 1)
                hit1 += pos == 0
                hit4 += pos < 4
        t = len(items)
        print(f"{name:<24}{hit1 / t:>8.2f}{hit4 / t:>8.2f}{rr / t:>9.2f}")
    print("\nhit@k: share of questions whose answer is in the top k chunks. MRR: mean of 1/rank of the first correct chunk.")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["generate", "run"])
    p.add_argument("meeting", help="path to a saved meeting JSON in outputs/")
    p.add_argument("--n", type=int, default=30)
    p.add_argument("--dataset", default=DATASET)
    a = p.parse_args()
    generate(a.meeting, a.n, a.dataset) if a.command == "generate" else run(a.meeting, a.dataset)
