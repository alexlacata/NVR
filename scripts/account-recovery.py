#!/usr/bin/env python3
"""Offline account recovery - for when someone is locked out of every
admin account (forgot password, lost the 2FA device/recovery codes) and
has no way back in through the web UI. Run this directly on the server
(or against the same NVR_DATA_DIR/.env the server uses), with the server
stopped if possible to avoid a concurrent write to users.yaml.

Usage (from the project root, with the venv active):
    python scripts/account-recovery.py list
    python scripts/account-recovery.py reset-password <username>
    python scripts/account-recovery.py disable-2fa <username>
    python scripts/account-recovery.py set-role <username> admin|viewer
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.models import UserRole  # noqa: E402
from app.user_store import LastAdminError, UserNotFound, UserStore, pwd_context  # noqa: E402


def _store() -> UserStore:
    settings = get_settings()
    print(f"(utilise {settings.users_file})")
    return UserStore(settings.users_file)


def cmd_list(_args: argparse.Namespace) -> int:
    users = _store().list()
    if not users:
        print("Aucun compte - le tout premier demarrage du serveur en creera un depuis NVR_ADMIN_USERNAME/NVR_ADMIN_PASSWORD.")
        return 0
    for u in users:
        twofa = "2FA activee" if u.totp_enabled else "2FA desactivee"
        print(f"  {u.username:<20} {u.role.value:<8} {twofa}")
    return 0


def cmd_reset_password(args: argparse.Namespace) -> int:
    store = _store()
    try:
        user = store.get(args.username)
    except UserNotFound:
        print(f"Compte introuvable : {args.username}", file=sys.stderr)
        return 1

    print(f"Compte : {user.username} ({user.role.value})")
    password = getpass.getpass("Nouveau mot de passe (8 caracteres minimum) : ")
    if len(password) < 8:
        print("Trop court (8 caracteres minimum).", file=sys.stderr)
        return 1
    confirm = getpass.getpass("Confirmez : ")
    if password != confirm:
        print("Les deux saisies ne correspondent pas.", file=sys.stderr)
        return 1

    store.set_password_hash(user.username, pwd_context.hash(password))
    print(f"Mot de passe de {user.username} reinitialise.")
    return 0


def cmd_disable_2fa(args: argparse.Namespace) -> int:
    store = _store()
    try:
        user = store.get(args.username)
    except UserNotFound:
        print(f"Compte introuvable : {args.username}", file=sys.stderr)
        return 1

    if not user.totp_enabled:
        print(f"La double authentification n'est deja pas active pour {user.username}.")
        return 0

    store.set_totp(user.username, secret=None, enabled=False)
    print(f"Double authentification desactivee pour {user.username} (les codes de secours sont aussi invalides).")
    return 0


def cmd_set_role(args: argparse.Namespace) -> int:
    from app.models import UserUpdate

    store = _store()
    try:
        store.get(args.username)
    except UserNotFound:
        print(f"Compte introuvable : {args.username}", file=sys.stderr)
        return 1

    try:
        store.update(args.username, UserUpdate(role=UserRole(args.role)))
    except LastAdminError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"{args.username} est maintenant {args.role}.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="Lister les comptes").set_defaults(func=cmd_list)

    p_reset = sub.add_parser("reset-password", help="Reinitialiser le mot de passe d'un compte")
    p_reset.add_argument("username")
    p_reset.set_defaults(func=cmd_reset_password)

    p_2fa = sub.add_parser("disable-2fa", help="Desactiver la 2FA d'un compte (perte du telephone et des codes de secours)")
    p_2fa.add_argument("username")
    p_2fa.set_defaults(func=cmd_disable_2fa)

    p_role = sub.add_parser("set-role", help="Changer le role d'un compte")
    p_role.add_argument("username")
    p_role.add_argument("role", choices=["admin", "viewer"])
    p_role.set_defaults(func=cmd_set_role)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
