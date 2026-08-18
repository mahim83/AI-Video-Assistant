import os
from langchain_mistralai import ChatMistralAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from core.vector_store import build_vector_store, load_vector_store, get_retriever

SYSTEM_PROMPT = """You are an expert meeting assistant. Answer the user's question
using the transcript context provided below.

The context is a verbatim transcript, so speakers refer to themselves in the first
person ("I", "my", "we"). When the user asks about "he", "she", "they", "the speaker"
or "the person", they mean whoever is talking in the transcript — read first-person
statements as statements about that person.

Only reply "I could not find this information in the meeting transcript." when the
context genuinely does not contain the answer. Do not refuse merely because the
question is worded differently from the transcript.

Always be concise and precise. If quoting someone, mention it clearly.

Context from meeting transcript:
{context}"""


def get_llm():
    return ChatMistralAI(
        model="mistral-small-latest",
        mistral_api_key=os.getenv("MISTRAL_API_KEY"),
        temperature=0.3,
    )

def format_docs(docs):
    return "\n\n".join([doc.page_content for doc in docs])


def _chain_from(vector_store):
    """Shared LCEL wiring, so build_ and load_ can never drift apart."""
    retriever = get_retriever(vector_store, k=4)

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


def load_rag_chain(collection_name: str = None):
    """Reopen a previously embedded meeting — no re-download, no re-transcribe."""
    return _chain_from(load_vector_store(collection_name=collection_name))


def ask_question(rag_chain, question: str) -> str:
    # No printing here — the caller owns display, otherwise every answer
    # gets echoed twice (once here, once by main.py's chat loop).
    return rag_chain.invoke(question)
