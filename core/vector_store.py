import os
import shutil
import sqlite3
from langchain_chroma import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

CHROMA_DIR = "vector_db"
COLLECTION_NAME = "meeting_transcript"
EMBEDDING_MODEL  = "all-MiniLM-L6-v2"
# Left in a deleted collection's vector folder when its files were locked.
DELETED_MARKER = "deleted.marker"

def get_embeddings():
    return HuggingFaceEmbeddings(
        model_name = EMBEDDING_MODEL,
        model_kwargs = {"device" : 'cpu'}
    )

def build_vector_store(transcript : str, collection_name : str = None)->Chroma:
    # Each meeting gets its own collection. With a single shared collection,
    # every new transcript piles into the same one and answers end up mixing
    # content from unrelated meetings.
    collection_name = collection_name or COLLECTION_NAME

    print("Building vector Store")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size = 500,
        chunk_overlap = 50
    )
    chunks = splitter.split_text(transcript)

    docs = [
        Document(page_content=chunk, metadata = {'chunk_index' : i})
        for i,chunk in enumerate(chunks)
    ]

    embeddings = get_embeddings()
    vector_store = Chroma.from_documents(
        documents= docs,
        embedding=embeddings,
        collection_name=collection_name,
        persist_directory=CHROMA_DIR
    )

    return vector_store



def _vector_dirs(collection_name : str) -> list:
    """Folders holding a collection's vectors, looked up in Chroma's own catalogue."""
    db = os.path.join(CHROMA_DIR, "chroma.sqlite3")
    if not os.path.isfile(db):
        return []
    con = sqlite3.connect(db)
    try:
        rows = con.execute(
            "SELECT s.id FROM segments s JOIN collections c ON s.collection = c.id "
            "WHERE c.name = ? AND s.scope = 'VECTOR'",
            (collection_name,),
        ).fetchall()
    except sqlite3.Error as e:
        # A Chroma upgrade changed its schema. Deleting still removes the
        # collection; only its vector files stay behind.
        print(f"⚠️ Could not locate vector files for {collection_name} ({e}).")
        return []
    finally:
        con.close()
    return [os.path.join(CHROMA_DIR, r[0]) for r in rows]


def delete_vector_store(collection_name : str):
    # The legacy shared collection holds several meetings; deleting it for one
    # of them would wipe the others' indexes.
    if collection_name == COLLECTION_NAME:
        return
    folders = _vector_dirs(collection_name)
    # Chroma opens (creating if needed) before deleting, so a meeting that
    # never had an index is handled too.
    Chroma(collection_name=collection_name, persist_directory=CHROMA_DIR).delete_collection()
    # delete_collection drops the rows from chroma.sqlite3 but leaves the
    # vector files on disk, so remove them here.
    for folder in folders:
        try:
            shutil.rmtree(folder)
        except PermissionError:
            # Windows keeps them locked while this process has the index open
            # (the meeting was loaded). Mark the folder for the next start.
            open(os.path.join(folder, DELETED_MARKER), "w").close()


def remove_deleted_dirs():
    """Finish deletes whose vector files were locked. Call before any index is opened."""
    if not os.path.isdir(CHROMA_DIR):
        return
    for name in os.listdir(CHROMA_DIR):
        folder = os.path.join(CHROMA_DIR, name)
        marker = os.path.join(folder, DELETED_MARKER)
        if os.path.isfile(marker):
            try:
                shutil.rmtree(folder)
            except OSError:
                # Still open in another running instance; rmtree may have taken
                # the marker already, so restore it and retry next start.
                open(marker, "w").close()



def load_vector_store(collection_name : str = None) ->Chroma:
    embeddings = get_embeddings()
    vector_store = Chroma(
        collection_name=collection_name or COLLECTION_NAME,
        embedding_function= embeddings,
        persist_directory=CHROMA_DIR
    )

    return vector_store
