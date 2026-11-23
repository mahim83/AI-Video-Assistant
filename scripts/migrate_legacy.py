"""
Copy meetings saved by the single-user version (outputs/*.json) into one
user's folder in the new per-user layout. Nothing is moved or deleted: once
you've checked the meetings open in the app, delete outputs/, vector_db/ and
downloads/ yourself. Search indexes are rebuilt from the transcript the first
time each meeting is opened.

    python -m scripts.migrate_legacy --email you@gmail.com   # for Google sign-in
    python -m scripts.migrate_legacy --local                 # for AUTH_MODE=off and the terminal app
"""
import argparse
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from core import storage            # noqa: E402  (after load_dotenv, for DATA_DIR)
from core.users import LOCAL_USER, user_id_for   # noqa: E402

LEGACY_DIR = "outputs"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    who = parser.add_mutually_exclusive_group(required=True)
    who.add_argument("--email", help="Google account that should own the meetings")
    who.add_argument("--local", action="store_true", help="the local user (AUTH_MODE=off, terminal app)")
    parser.add_argument("--source", default=LEGACY_DIR, help="folder with the old meeting files")
    args = parser.parse_args()

    user_id = LOCAL_USER.id if args.local else user_id_for(args.email)
    space = storage.user_space(user_id)
    if not os.path.isdir(args.source):
        sys.exit(f"No folder {args.source!r}; nothing to migrate.")

    existing = set(storage.list_meetings(space))
    copied = skipped = 0
    for name in sorted(os.listdir(args.source)):
        if not storage.MEETING_FILE_RE.fullmatch(name):
            continue
        if name in existing:
            print(f"  skip  {name} (already there)")
            skipped += 1
            continue
        with open(os.path.join(args.source, name), encoding="utf-8") as f:
            meeting = json.load(f)
        # Its audio list pointed into downloads/, which the new version doesn't use.
        meeting.pop("audio_files", None)
        saved_at = meeting.pop("saved_at", None)
        source = meeting.pop("source", "")
        path = storage.save_meeting(space, meeting, source)
        if saved_at:   # keep the original date rather than today's
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            data["saved_at"] = saved_at
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"  copy  {name}")
        copied += 1

    print(f"\n{copied} copied, {skipped} skipped, into {space.meetings_dir}")


if __name__ == "__main__":
    main()
