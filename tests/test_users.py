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


def test_list_users_shows_sources(owner):
    users.add_user(owner, "added@example.com")
    sources = {r["email"]: r["source"] for r in users.list_users(owner)}
    assert sources == {
        "owner@example.com": "ADMIN_EMAILS",
        "friend@example.com": "ALLOWED_EMAILS",
        "added@example.com": "app",
    }
