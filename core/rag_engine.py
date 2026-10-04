import os
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from core.vector_store import build_vector_store, load_vector_store
from core.retriever import hybrid_retriever

SYSTEM_PROMPT = """You are a helpful video assistant. Use the transcript context below
to answer questions about the video's content.

The context is a verbatim transcript, so speakers refer to themselves in the first
person ("I", "my", "we"). When the user asks about "he", "she", "they", "the speaker"
or "the person", they mean whoever is talking in the transcript — read first-person
statements as statements about that person.

For greetings, thanks, acknowledgments (such as "ok" or "nice"), and other casual
conversation, respond naturally and briefly; do not search the transcript for an answer.
For questions unrelated to the video, answer as a general assistant and make clear
when the answer is not based on the transcript.
If the user asks about the video's content and the transcript genuinely does not
contain the answer, say so briefly and invite them to ask about another part of the video.
Do not refuse merely because a video-related question is worded differently from the transcript.

Always be concise and precise. If quoting someone, mention it clearly.

Context from meeting transcript:
{context}"""


def get_llm():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set in environment / .env")
    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        api_key=api_key,
        temperature=0.3,
    )

def format_docs(docs):
    return "\n\n".join([doc.page_content for doc in docs])


def _chain_from(vector_store):
    """Shared LCEL wiring, so build_ and load_ can never drift apart."""
    retriever = hybrid_retriever(vector_store)

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", "{question}"),
    ])

    return (
        {
            "context": retriever | RunnableLambda(format_docs),
            "question": RunnablePassthrough(),
        }
        | prompt
        | get_llm()
        | StrOutputParser()
    )


def build_rag_chain(transcript: str, collection_name: str = None):
    """Embed a fresh transcript and return a chain over it."""
    return _chain_from(build_vector_store(transcript, collection_name=collection_name))


def load_rag_chain(collection_name: str = None, transcript: str = None):
    """Reopen a saved index, rebuilding it from the transcript if it is empty."""
    vector_store = load_vector_store(collection_name=collection_name)
    if transcript and vector_store._collection.count() == 0:
        vector_store = build_vector_store(transcript, collection_name=collection_name)
    return _chain_from(vector_store)


def ask_question(rag_chain, question: str) -> str:
    # No printing here — the caller owns display, otherwise every answer
    # gets echoed twice (once here, once by main.py's chat loop).
    return rag_chain.invoke(question)
