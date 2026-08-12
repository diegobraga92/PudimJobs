"""Unit tests for the secret encryption helpers (no DB required)."""

import pytest
from cryptography.fernet import InvalidToken

from app.services.secrets import decrypt_secret, encrypt_secret, mask_secret


def test_encrypt_decrypt_roundtrip():
    token = encrypt_secret("super-secret-value")
    assert token != "super-secret-value"
    assert decrypt_secret(token) == "super-secret-value"


def test_encryption_is_randomized():
    token_a = encrypt_secret("same-value")
    token_b = encrypt_secret("same-value")
    assert token_a != token_b
    assert decrypt_secret(token_a) == decrypt_secret(token_b) == "same-value"


def test_mask_secret():
    assert mask_secret("sk-abcdefghijklmnop") == "sk-a…mnop"
    assert mask_secret(None) is None
    assert mask_secret("short") == "••••••••"


def test_decrypt_invalid_token_raises():
    with pytest.raises(InvalidToken):
        decrypt_secret("not-a-valid-token")
