"""
Per-user storage. Every user gets their own folder:

    DATA_DIR/users/<user id>/meetings/*.json   saved meetings
    DATA_DIR/users/<user id>/vector_db/        their Chroma indexes
    DATA_DIR/users/<user id>/work/<job>/       audio while a video is processed

Authorization for meetings is structural: every function takes the caller's
UserSpace, and a meeting name can only resolve inside that user's folder, so
one user's request can't reach another user's files.
"""
import json
import os
import re
import shutil
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime

from core.settings import get_settings
from core.vector_store import delete_vector_store, remove_deleted_dirs

USER_ID_RE = re.compile(r"^[a-z0-9]{1,64}$")
# Names come from _slug() + a timestamp: letters, digits, "_" and "-".
MEETING_FILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,120}\.json$")


@dataclass(frozen=True)
class UserSpace:
    user_id: str
    root: str

    @property
    def meetings_dir(self) -> str:
        return os.path.join(self.root, "meetings")

    @property
    def vector_dir(self) -> str:
        return os.path.join(self.root, "vector_db")

    @property
    def work_dir(self) -> str:
        return os.path.join(self.root, "work")


def user_space(user_id: str) -> UserSpace:
    if not USER_ID_RE.fullmatch(user_id or ""):
        raise ValueError("invalid user id")
    return UserSpace(user_id, os.path.join(get_settings().data_dir, "users", user_id))


def _meeting_path(space: UserSpace, filename: str) -> str:
    if not MEETING_FILE_RE.fullmatch(filename or ""):
        raise ValueError("invalid meeting name")
    path = os.path.join(space.meetings_dir, filename)
    # The pattern already rules out separators and "..". Check the resolved
    # folder too, so a future change to the pattern can't open a hole.
    if os.path.dirname(os.path.abspath(path)) != os.path.abspath(space.meetings_dir):
        raise ValueError("invalid meeting name")
    return path


def save_meeting(space: UserSpace, result: dict, source: str) -> str:
    """Persist everything except the rag_chain, which is a live object."""
    os.makedirs(space.meetings_dir, exist_ok=True)
    payload = {k: v for k, v in result.items() if k != "rag_chain"}
    payload["source"] = source
    payload["owner"] = space.user_id
    payload["saved_at"] = datetime.now().isoformat(timespec="seconds")

    path = _meeting_path(space, payload["collection_name"] + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def list_meetings(space: UserSpace) -> list:
    if not os.path.isdir(space.meetings_dir):
        return []
    return sorted(f for f in os.listdir(space.meetings_dir) if MEETING_FILE_RE.fullmatch(f))


def load_meeting(space: UserSpace, filename: str) -> dict:
    with open(_meeting_path(space, filename), encoding="utf-8") as f:
        return json.load(f)


def delete_meeting(space: UserSpace, filename: str):
    """
    Remove a saved meeting and its search index. The JSON goes last, so a
    failure part-way leaves it listed and the delete can be retried.
    """
    path = _meeting_path(space, filename)
    meeting = load_meeting(space, filename)
    delete_vector_store(meeting["collection_name"], persist_directory=space.vector_dir)
    os.remove(path)


@contextmanager
def job_dir(space: UserSpace):
    """
    A fresh folder for one video's audio, deleted when the block ends,
    whether it succeeded or failed. Audio isn't needed once the transcript
    exists, and a long video's WAV and chunks take hundreds of MB.
    """
    path = os.path.join(space.work_dir, uuid.uuid4().hex)
    os.makedirs(path)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


# Older than any real job. A younger folder may belong to a job running in
# another process (the CLI and the web app at the same time), so it stays.
STALE_JOB_SECONDS = 12 * 3600


def cleanup_on_start():
    """
    Run once per process, before any index is opened: finish index deletes
    that Windows had locked, and remove audio left by a crash or restart
    mid-job.
    """
    users_dir = os.path.join(get_settings().data_dir, "users")
    if not os.path.isdir(users_dir):
        return
    cutoff = datetime.now().timestamp() - STALE_JOB_SECONDS
    for user_id in os.listdir(users_dir):
        if not USER_ID_RE.fullmatch(user_id):
            continue
        space = user_space(user_id)
        remove_deleted_dirs(space.vector_dir)
        if os.path.isdir(space.work_dir):
            for job in os.listdir(space.work_dir):
                path = os.path.join(space.work_dir, job)
                if os.path.getmtime(path) < cutoff:
                    shutil.rmtree(path, ignore_errors=True)
