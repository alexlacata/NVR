from app.secrets_crypto import SecretsCipher


def test_encrypt_then_decrypt_roundtrips():
    cipher = SecretsCipher("some-secret-key")
    ciphertext = cipher.encrypt("my-totp-secret")
    assert ciphertext != "my-totp-secret"
    assert cipher.decrypt(ciphertext) == "my-totp-secret"


def test_empty_string_passes_through_unchanged():
    cipher = SecretsCipher("some-secret-key")
    assert cipher.encrypt("") == ""
    assert cipher.decrypt("") == ""


def test_decrypting_plaintext_returns_it_unchanged():
    # A value written before this feature existed (or under a different
    # key) isn't a valid Fernet token - must not raise, so upgrading
    # doesn't brick an existing setup.
    cipher = SecretsCipher("some-secret-key")
    assert cipher.decrypt("plain-old-value") == "plain-old-value"


def test_different_keys_produce_different_ciphertext():
    a = SecretsCipher("key-a")
    b = SecretsCipher("key-b")
    ciphertext = a.encrypt("shared-plaintext")
    assert ciphertext != b.encrypt("shared-plaintext")
    # b can't decrypt what a encrypted - falls back to returning it as-is
    assert b.decrypt(ciphertext) == ciphertext
