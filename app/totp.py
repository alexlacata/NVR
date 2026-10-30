"""Minimal RFC 6238 TOTP (Google Authenticator/Authy-compatible) - hand-
rolled from stdlib hmac/hashlib/base64 rather than pulling in a dependency
for ~40 lines of well-specified, stable math, in keeping with the rest of
this codebase (the hand-rolled ONVIF/WS-Discovery clients, the stdlib-only
PNG icons)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
import urllib.parse
from typing import Optional

_STEP_SECONDS = 30
_DIGITS = 6


def generate_secret() -> str:
    """A random base32 secret, the form authenticator apps expect."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii")


def _hotp(secret: str, counter: int) -> str:
    padded = secret.upper() + "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (int.from_bytes(digest[offset:offset + 4], "big") & 0x7FFFFFFF) % (10 ** _DIGITS)
    return str(code).zfill(_DIGITS)


def totp_now(secret: str, at: Optional[float] = None) -> str:
    counter = int((at if at is not None else time.time()) // _STEP_SECONDS)
    return _hotp(secret, counter)


def verify_totp(secret: str, code: str, window: int = 1, at: Optional[float] = None) -> bool:
    """Accepts a code from the current 30s step or `window` steps before/
    after, to tolerate minor clock drift between the server and the phone."""
    if not secret or not code or not code.strip().isdigit():
        return False
    code = code.strip()
    now = at if at is not None else time.time()
    counter = int(now // _STEP_SECONDS)
    for offset in range(-window, window + 1):
        if hmac.compare_digest(_hotp(secret, counter + offset), code):
            return True
    return False


def provisioning_uri(secret: str, username: str, issuer: str = "Fléau") -> str:
    """otpauth:// URI a QR code can encode for an authenticator app."""
    label = urllib.parse.quote(f"{issuer}:{username}")
    params = urllib.parse.urlencode({
        "secret": secret, "issuer": issuer, "algorithm": "SHA1", "digits": _DIGITS, "period": _STEP_SECONDS,
    })
    return f"otpauth://totp/{label}?{params}"


# Excludes visually ambiguous characters (0/O, 1/I/L) so a code copied down
# by hand is less likely to be mistyped.
_RECOVERY_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def generate_recovery_codes(count: int = 8) -> list[str]:
    """One-time backup codes for when the authenticator app/device is lost -
    each is meant to be hashed (like a password) before storage and
    consumed (deleted) on use, never stored or compared in plaintext."""
    codes = []
    for _ in range(count):
        raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(8))
        codes.append(f"{raw[:4]}-{raw[4:]}")
    return codes
