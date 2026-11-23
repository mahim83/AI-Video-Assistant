import os
import time

import pytest

from core import storage


def _meeting(name="weekly_sync_20260101_120000"):
    return {"title": "Weekly sync", "transcript": "hello", "summary": "- hi", "collection_name": name}


@pytest.mark.parametrize("user_id", ["", "../x", "a/b", "ABC", "a" * 65, "x\\y"])
def test_bad_user_ids(user_id):
    with pytest.raises(ValueError):
        storage.user_space(user_id)


@pytest.mark.parametrize("name", [
    "../other.json", "..\\other.json", "a/b.json", "/etc/passwd", "C:\\x.json",
    ".json", "x.txt", "x.json/../../y.json", "_hidden.json", "",
])
def test_meeting_names_cannot_escape(name):
    space = storage.user_space("alice")
    with pytest.raises(ValueError):
        storage.load_meeting(space, name)


def test_users_only_see_their_own_meetings():
    alice, bob = storage.user_space("alice"), storage.user_space("bob")
    path = storage.save_meeting(alice, _meeting(), "https://youtu.be/x")

    assert storage.list_meetings(alice) == ["weekly_sync_20260101_120000.json"]
    assert storage.list_meetings(bob) == []
    # Bob naming Alice's meeting looks only in Bob's folder.
    with pytest.raises(FileNotFoundError):
        storage.load_meeting(bob, "weekly_sync_20260101_120000.json")

    saved = storage.load_meeting(alice, "weekly_sync_20260101_120000.json")
    assert saved["owner"] == "alice" and "rag_chain" not in saved
    assert os.path.abspath(os.path.dirname(path)) == os.path.abspath(alice.meetings_dir)


def test_delete_meeting():
    alice = storage.user_space("alice")
    storage.save_meeting(alice, _meeting(), "src")
    storage.delete_meeting(alice, "weekly_sync_20260101_120000.json")
    assert storage.list_meetings(alice) == []


def test_job_dir_is_removed_even_on_failure():
    space = storage.user_space("alice")
    with pytest.raises(RuntimeError):
        with storage.job_dir(space) as work:
            open(os.path.join(work, "audio.wav"), "w").close()
            raise RuntimeError("transcription failed")
    assert not os.path.exists(work)


def test_cleanup_removes_only_stale_jobs():
    space = storage.user_space("alice")
    stale = os.path.join(space.work_dir, "stale")
    fresh = os.path.join(space.work_dir, "fresh")
    os.makedirs(stale)
    os.makedirs(fresh)
    old = time.time() - storage.STALE_JOB_SECONDS - 60
    os.utime(stale, (old, old))

    storage.cleanup_on_start()
    assert not os.path.exists(stale) and os.path.exists(fresh)
