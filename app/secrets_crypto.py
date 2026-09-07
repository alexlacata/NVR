"""Symmetric encryption for secrets stored at rest (SMTP password, TOTP
secrets) - defends against disk/backup theft exposing them in plaintext,
by deriving an encryption key from NVR_SECRET_KEY (the same key already
used to sign session tokens). This does not protect against compromise of
the running server itself: the key is always available to the process so
it can decrypt on read, same tradeoff as full-disk encryption. Password
hashes and recovery codes are not covered here - they're already one-way
hashed, which is a stronger property than encryption for something that's
only ever compared, never needed back in plaintext."""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


def _derive_key(secret_key: str) -> bytes:
    digest = hashlib.sha256(f"nvr-secrets-encryption:{secret_key}".encode()).digest()
    return base64.urlsafe_b64encode(digest)


class SecretsCipher:
    def __init__(self, secret_key: str):
        self._fernet = Fernet(_derive_key(secret_key))

    def encrypt(self, plaintext: str) -> str:
        if not plaintext:
            return plaintext
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, value: str) -> str:
        """Decrypts `value`; if it isn't a value this cipher encrypted (a
        plaintext secret from before this feature existed, or one written
        under a different NVR_SECRET_KEY), it's returned unchanged rather
        than raising - so enabling this doesn't brick an existing setup,
        and a plaintext value just gets encrypted on its next write."""
        if not value:
            return value
        try:
            return self._fernet.decrypt(value.encode()).decode()
        except InvalidToken:
            return value
