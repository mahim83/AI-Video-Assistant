import pytest

from core import db, users
from core.errors import AccessDenied


def test_env_admin_and_allowed_user():
    admin = users.authorize("Owner@Example.com ", True)
    assert (admin.email, admin.role) == ("owner@example.com", "admin")
    friend = users.authorize("friend@example.com", "true")
    assert friend.role == "user"


@pytest.mark.parametrize("email,verified", [
    ("stranger@example.com", True),     # not invited
    ("friend@example.com", False),      # invited but unverified
    ("friend@example.com", None),       # provider didn't say
    ("", True),
    (None, True),
])
def test_denied(email, verified):
    with pytest.raises(AccessDenied):
        users.authorize(email, verified)


def test_user_id_is_stable_and_hides_email():
    uid = users.user_id_for("Friend@Example.com")
    assert uid == users.user_id_for("friend@example.com")
    assert len(uid) == 16 and "friend" not in uid


def test_admin_adds_and_revokes(owner, friend):
    users.add_user(owner, "New@Example.com", "user")
    assert users.authorize("new@example.com", True).role == "user"

    users.add_user(owner, "new@example.com", "admin")   # role change
    assert users.authorize("new@example.com", True).is_admin

    users.remove_user(owner, "new@example.com")
    with pytest.raises(AccessDenied):
        users.authorize("new@example.com", True)

    actions = [r["action"] for r in db.recent_audit()]
    assert actions.count("user_added") == 2 and "user_removed" in actions


def test_only_admins_manage_users(friend):
    with pytest.raises(PermissionError):
        users.add_user(friend, "x@example.com")
    with pytest.raises(PermissionError):
        users.remove_user(friend, "x@example.com")
    with pytest.raises(PermissionError):
        users.list_users(friend)


def test_admin_guard_rails(owner):
    with pytest.raises(ValueError):
        users.add_user(owner, "not-an-email")
    with pytest.raises(ValueError):
        users.add_user(owner, "x@example.com", "superuser")
    with pytest.raises(ValueError):
        users.remove_user(owner, "owner@example.com")      # self
    with pytest.raises(ValueError):
        users.remove_user(owner, "friend@example.com")     # set in .env
    with pytest.raises(ValueError):
        users.remove_user(owner, "nobody@example.com")


def test_registering_lets_people_straight_in():
    with pytest.raises(users.NotInvited):
        users.authorize("new@example.com", True)
    user = users.register("New@Example.com", sub="g-1", name="New Comer")
    assert (user.email, user.role) == ("new@example.com", "user")
    assert users.authorize("new@example.com", True, sub="g-1").role == "user"
    users.register("new@example.com", sub="g-1")       # a second click changes nothing
    actions = [r["action"] for r in db.recent_audit()]
    assert actions.count("user_registered") == 1


def test_revoked_user_cannot_register_again(owner):
    users.register("pest@example.com")
    users.remove_user(owner, "pest@example.com")
    with pytest.raises(AccessDenied, match="revoked"):
        users.authorize("pest@example.com", True)
    with pytest.raises(AccessDenied, match="revoked"):
        users.register("pest@example.com")
    # An admin can let them back in.
    users.add_user(owner, "pest@example.com")
    assert users.authorize("pest@example.com", True).role == "user"
    assert not users.is_revoked("pest@example.com")


def test_old_requests_carry_over():
    """Rows from the approve-first sign-up: a rejection still keeps someone out."""
    with db.connect() as con:
        con.execute("INSERT INTO access_requests (email, status, requested_at) VALUES "
                    "('waiting@example.com', 'pending', 0), ('declined@example.com', 'rejected', 0)")
    users.register("waiting@example.com")
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM access_requests WHERE email = 'waiting@example.com'"
                           ).fetchone()[0] == 0
    with pytest.raises(AccessDenied, match="revoked"):
        users.register("declined@example.com")


def test_invite_mode_refuses_registration(monkeypatch):
    from core.settings import get_settings
    monkeypatch.setenv("SIGNUP_MODE", "invite")
    get_settings.cache_clear()
    with pytest.raises(AccessDenied, match="invitation"):
        users.register("new@example.com")


def test_old_request_setting_means_open(monkeypatch):
    from core.settings import get_settings
    monkeypatch.setenv("SIGNUP_MODE", "request")
    get_settings.cache_clear()
    assert get_settings().signup_mode == "open"


def test_list_users_shows_sources(owner):
    users.add_user(owner, "added@example.com")
    users.register("joined@example.com")
    sources = {r["email"]: r["source"] for r in users.list_users(owner)}
    assert sources == {
        "owner@example.com": "ADMIN_EMAILS",
        "friend@example.com": "ALLOWED_EMAILS",
        "added@example.com": "app",
        "joined@example.com": "sign-up",
    }


def test_signed_up_users_can_be_managed_and_show_their_name(owner):
    """The bug: people who signed up themselves were missing from the admin's revoke list."""
    users.register("srao@example.com", sub="g-9", name="S Rao")
    row = next(r for r in users.list_users(owner) if r["email"] == "srao@example.com")
    assert row["source"] == "sign-up" and row["name"] == "S Rao"
    assert users.label(row) == "S Rao (srao@example.com)"

    users.set_role(owner, "srao@example.com", "admin")
    assert users.authorize("srao@example.com", True, sub="g-9").is_admin
    users.set_role(owner, "srao@example.com", "user")

    users.remove_user(owner, "srao@example.com")
    revoked = users.list_revoked(owner)
    assert [(r["email"], r["name"]) for r in revoked] == [("srao@example.com", "S Rao")]
    users.restore_user(owner, "srao@example.com")
    assert users.authorize("srao@example.com", True, sub="g-9").role == "user"
    assert users.list_revoked(owner) == []
    assert users.label(next(r for r in users.list_users(owner) if r["email"] == "srao@example.com")) \
        == "S Rao (srao@example.com)"


def test_user_details(owner):
    from core import storage
    users.register("srao@example.com", sub="g-9", name="S Rao")
    db.audit("login", email="srao@example.com")
    uid = users.user_id_for("srao@example.com")
    db.record_event(uid, "video")
    db.record_event(uid, "question", 3)
    space = storage.user_space(uid)
    import os
    os.makedirs(space.meetings_dir)
    open(os.path.join(space.meetings_dir, "talk_20260101.json"), "w").write("{}")

    row = next(r for r in users.user_details(owner) if r["email"] == "srao@example.com")
    assert row["method"] == "Google"
    assert row["joined"] and row["last_sign_in"]
    assert row["meetings"] == 1
    assert row["today"]["video"] == 1 and row["total"]["question"] == 3


def test_google_name_is_filled_in_later():
    users.register("old@example.com")                 # signed up before names were kept
    users.remember_name("old@example.com", "Old Timer")
    users.remember_name("old@example.com", "Someone Else")   # never overwrites
    owner = users.authorize("owner@example.com", True)
    assert users.label(next(r for r in users.list_users(owner) if r["email"] == "old@example.com")) \
        == "Old Timer (old@example.com)"


def test_delete_user_removes_everything(owner):
    import os
    from core import storage
    users.register("gone@example.com", sub="g-1", name="Gone")
    uid = users.user_id_for("gone@example.com")
    space = storage.user_space(uid)
    os.makedirs(space.meetings_dir)
    db.record_event(uid, "video")

    users.delete_user(owner, "gone@example.com", block=False)
    assert not os.path.exists(space.root)
    assert "gone@example.com" not in [r["email"] for r in users.list_users(owner)]
    assert db.total_since(uid, "video", 0) == 0
    with db.connect() as con:
        assert con.execute("SELECT 1 FROM identities WHERE email = 'gone@example.com'").fetchone() is None
    users.register("gone@example.com", sub="g-2")     # not blocked: a fresh start is allowed

    users.delete_user(owner, "gone@example.com")      # blocked by default
    with pytest.raises(AccessDenied, match="revoked"):
        users.register("gone@example.com")
    assert [r["email"] for r in users.list_revoked(owner)] == ["gone@example.com"]
    assert "user_deleted" in [r["action"] for r in db.recent_audit()]


def test_manage_guard_rails(owner, friend):
    users.register("x@example.com")
    for fn in (lambda: users.set_role(friend, "x@example.com", "admin"),
               lambda: users.delete_user(friend, "x@example.com"),
               lambda: users.list_revoked(friend),
               lambda: users.user_details(friend)):
        with pytest.raises(PermissionError):
            fn()
    with pytest.raises(ValueError):
        users.set_role(owner, "owner@example.com", "user")       # yourself
    with pytest.raises(ValueError):
        users.delete_user(owner, "friend@example.com")           # set in .env
    with pytest.raises(ValueError):
        users.set_role(owner, "x@example.com", "superuser")
    with pytest.raises(ValueError):
        users.delete_user(owner, "nobody@example.com")
    with pytest.raises(ValueError):
        users.restore_user(owner, "x@example.com")               # not revoked
