"""Runs scripts/account-recovery.py as a real subprocess against a real
users.yaml (created via UserStore directly, same as the app would) -
faithful to how this script is actually invoked (a separate process
against the deployed data directory), not just its functions in-process."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from app.models import UserCreate, UserRole
from app.user_store import UserStore, pwd_context

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "account-recovery.py"


def _run(env_data_dir: Path, args: list[str], input_text: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=input_text,
        capture_output=True,
        text=True,
        env={**os.environ, "NVR_DATA_DIR": str(env_data_dir)},
        timeout=30,
    )


def _seed_store(tmp_path: Path) -> UserStore:
    store = UserStore(tmp_path / "config" / "users.yaml")
    store.create(UserCreate(username="admin", password="origpass123", role=UserRole.admin))
    return store


def test_list_shows_accounts(tmp_path):
    _seed_store(tmp_path)
    result = _run(tmp_path, ["list"])
    assert result.returncode == 0
    assert "admin" in result.stdout
    assert "2FA desactivee" in result.stdout


def test_list_empty_when_no_accounts(tmp_path):
    result = _run(tmp_path, ["list"])
    assert result.returncode == 0
    assert "Aucun compte" in result.stdout


def test_reset_password_updates_hash(tmp_path):
    _seed_store(tmp_path)
    result = _run(tmp_path, ["reset-password", "admin"], input_text="newpassword1\nnewpassword1\n")
    assert result.returncode == 0
    assert "reinitialise" in result.stdout

    store = UserStore(tmp_path / "config" / "users.yaml")
    user = store.get("admin")
    assert pwd_context.verify("newpassword1", user.password_hash)
    assert not pwd_context.verify("origpass123", user.password_hash)


def test_reset_password_rejects_short_password(tmp_path):
    _seed_store(tmp_path)
    result = _run(tmp_path, ["reset-password", "admin"], input_text="short\nshort\n")
    assert result.returncode == 1
    assert "8 caracteres" in result.stdout + result.stderr


def test_reset_password_rejects_mismatched_confirmation(tmp_path):
    _seed_store(tmp_path)
    result = _run(tmp_path, ["reset-password", "admin"], input_text="firstpassword\nsecondpassword\n")
    assert result.returncode == 1
    assert "correspondent" in result.stdout + result.stderr


def test_reset_password_unknown_user(tmp_path):
    _seed_store(tmp_path)
    result = _run(tmp_path, ["reset-password", "nobody"], input_text="")
    assert result.returncode == 1
    assert "introuvable" in result.stdout + result.stderr


def test_disable_2fa_clears_secret_and_codes(tmp_path):
    store = _seed_store(tmp_path)
    store.set_totp("admin", secret="ABCDEF", enabled=True)
    store.set_totp_recovery_codes("admin", [pwd_context.hash("AAAA-BBBB")])

    result = _run(tmp_path, ["disable-2fa", "admin"])
    assert result.returncode == 0
    assert "desactivee" in result.stdout

    store2 = UserStore(tmp_path / "config" / "users.yaml")
    user = store2.get("admin")
    assert user.totp_enabled is False
    assert user.totp_secret is None
    assert user.totp_recovery_codes == []


def test_disable_2fa_noop_when_already_disabled(tmp_path):
    _seed_store(tmp_path)
    result = _run(tmp_path, ["disable-2fa", "admin"])
    assert result.returncode == 0
    assert "deja pas active" in result.stdout


def test_set_role_changes_role(tmp_path):
    store = _seed_store(tmp_path)
    store.create(UserCreate(username="bob", password="viewerpass1", role=UserRole.viewer))

    result = _run(tmp_path, ["set-role", "bob", "admin"])
    assert result.returncode == 0

    store2 = UserStore(tmp_path / "config" / "users.yaml")
    assert store2.get("bob").role == UserRole.admin


def test_set_role_refuses_to_demote_last_admin(tmp_path):
    _seed_store(tmp_path)
    result = _run(tmp_path, ["set-role", "admin", "viewer"])
    assert result.returncode == 1
    assert "administrateur" in result.stdout + result.stderr

    store2 = UserStore(tmp_path / "config" / "users.yaml")
    assert store2.get("admin").role == UserRole.admin
