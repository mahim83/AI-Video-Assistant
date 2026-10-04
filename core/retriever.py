import os
import re
from rank_bm25 import BM25Okapi
from langchain_core.documents import Document
from langchain_core.runnables import RunnableLambda

# Local cross-encoder, downloaded once (~90MB) and run on CPU.
RERANK_MODEL = os.getenv("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L6-v2")

# Filler words carry no signal for keyword matching, and in BM25 they let
# "what did he say about X" match every chunk where the speaker says anything.
STOPWORDS = frozenset("""
a an and are as at be but by did do does for from had has have he her his how i if in
is it its me my of on or our she so than that the their them they this to us was we
were what when where which who why will with would you your about say said talk tell
""".split())

_reranker = None        # the loaded CrossEncoder, or None until a load succeeds
_reranker_error = None  # why the last load attempt failed, shown in the UI


def load_reranker():
    global _reranker, _reranker_error

    if _reranker is None:
        try:
            # Imported lazily for the same reason as Whisper: it pulls in torch.
            from sentence_transformers import CrossEncoder

            print(f"Loading reranker: {RERANK_MODEL} ...")
            _reranker = CrossEncoder(RERANK_MODEL, device="cpu", max_length=512)
            _reranker_error = None
            print("Reranker loaded.")
        except Exception as e:
            # Typically the first run while offline. Chat still works on the
            # fused ranking, and the next index build tries again, so a brief
            # outage doesn't disable reranking until the app restarts.
            _reranker_error = f"{type(e).__name__}: {e}"
            print(f"⚠️ Reranker unavailable ({_reranker_error}). Using hybrid ranking only.")
    return _reranker


def reranker_error():
    """Why the last load attempt failed, or None if the reranker is loaded."""
    return _reranker_error


def _tokenize(text: str) -> list:
    return [t for t in re.findall(r"\w+", text.lower()) if t not in STOPWORDS]


def _fuse(rankings: list, c: int = 60) -> list:
    """
    Reciprocal Rank Fusion. BM25 and cosine scores live on different scales,
    so combine ranks rather than raw scores.
    """
    scores, by_text = {}, {}
    for ranking in rankings:
        for rank, doc in enumerate(ranking):
            # Keyed by text, not chunk_index: the legacy shared collection holds
            # several meetings, so chunk_index alone is not unique there.
            by_text.setdefault(doc.page_content, doc)
            scores[doc.page_content] = scores.get(doc.page_content, 0) + 1 / (c + rank + 1)
    return [by_text[t] for t in sorted(scores, key=scores.get, reverse=True)]


def hybrid_retriever(vector_store, k: int = 4, fetch_k: int = 20):
    """
    Vector search finds paraphrases; BM25 finds exact names, numbers and jargon
    that embeddings blur. Take fetch_k from each, fuse, then let a cross-encoder
    (which reads question and chunk together) pick the best k.

    The BM25 index is built from the chunks already stored in Chroma, so saved
    meetings work without re-indexing.
    """
    stored = vector_store.get(include=["documents", "metadatas"])
    docs = [
        Document(page_content=text, metadata=meta or {})
        for text, meta in zip(stored["documents"], stored["metadatas"])
    ]
    corpus = [_tokenize(d.page_content) for d in docs]
    # BM25Okapi divides by average document length, so an all-empty corpus
    # (a silent video) would raise ZeroDivisionError.
    bm25 = BM25Okapi(corpus) if any(corpus) else None

    # Load (or retry) now, so the delay lands on "Building index", not the
    # first question.
    load_reranker()

    def retrieve(question: str) -> list:
        if not docs:
            return []

        n = min(fetch_k, len(docs))
        dense = vector_store.similarity_search(question, k=n)

        keyword = []
        if bm25:
            scores = bm25.get_scores(_tokenize(question))
            top = sorted(range(len(docs)), key=lambda i: scores[i], reverse=True)[:n]
            # Zero means no shared terms; such chunks are noise, not candidates.
            keyword = [docs[i] for i in top if scores[i] > 0]

        candidates = _fuse([dense, keyword])
        # Read the module-level model, not a copy captured at build time, so a
        # chain built during an outage starts reranking once a later load works.
        if _reranker is not None:
            relevance = _reranker.predict([(question, d.page_content) for d in candidates])
            ranked = sorted(zip(relevance, candidates), key=lambda p: p[0], reverse=True)
            candidates = [d for _, d in ranked]
        return candidates[:k]

    return RunnableLambda(retrieve)
