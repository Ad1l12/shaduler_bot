import pytest
from cryptography.fernet import Fernet
from unittest.mock import patch

from src.security.encryption import EncryptionError, decrypt_token, encrypt_token


VALID_KEY = Fernet.generate_key().decode()


def _with_key(key: str) -> dict[str, str]:
    """Helper: patch settings.encryption_key with the given key."""
    return {"src.security.encryption.settings": type("S", (), {"encryption_key": key})()}


# ── Round-trip ────────────────────────────────────────────────────────────────

def test_roundtrip_simple() -> None:
    with patch("src.security.encryption.settings") as mock:
        mock.encryption_key = VALID_KEY
        token = "my-secret-access-token"
        assert decrypt_token(encrypt_token(token)) == token


def test_roundtrip_unicode() -> None:
    with patch("src.security.encryption.settings") as mock:
        mock.encryption_key = VALID_KEY
        token = "токен-на-русском-языке"
        assert decrypt_token(encrypt_token(token)) == token


def test_roundtrip_long_token() -> None:
    with patch("src.security.encryption.settings") as mock:
        mock.encryption_key = VALID_KEY
        token = "x" * 4096
        assert decrypt_token(encrypt_token(token)) == token


# ── Empty string ──────────────────────────────────────────────────────────────

def test_encrypt_empty_string() -> None:
    with patch("src.security.encryption.settings") as mock:
        mock.encryption_key = VALID_KEY
        ciphertext = encrypt_token("")
        assert decrypt_token(ciphertext) == ""


# ── Ciphertext is bytes, not str ──────────────────────────────────────────────

def test_encrypt_returns_bytes() -> None:
    with patch("src.security.encryption.settings") as mock:
        mock.encryption_key = VALID_KEY
        result = encrypt_token("token")
        assert isinstance(result, bytes)


def test_decrypt_returns_str() -> None:
    with patch("src.security.encryption.settings") as mock:
        mock.encryption_key = VALID_KEY
        ciphertext = encrypt_token("token")
        result = decrypt_token(ciphertext)
        assert isinstance(result, str)


# ── Different keys produce different ciphertexts ─────────────────────────────

def test_different_ciphertexts_same_plaintext() -> None:
    with patch("src.security.encryption.settings") as mock:
        mock.encryption_key = VALID_KEY
        ct1 = encrypt_token("same-value")
        ct2 = encrypt_token("same-value")
        # Fernet uses random IV — ciphertexts must differ
        assert ct1 != ct2


# ── Invalid key raises EncryptionError ───────────────────────────────────────

def test_decrypt_with_wrong_key_raises() -> None:
    """Decrypting with a different valid key must raise, NOT return garbage."""
    key1 = Fernet.generate_key().decode()
    key2 = Fernet.generate_key().decode()

    with patch("src.security.encryption.settings") as mock:
        mock.encryption_key = key1
        ciphertext = encrypt_token("secret")

    with patch("src.security.encryption.settings") as mock:
        mock.encryption_key = key2
        with pytest.raises(EncryptionError):
            decrypt_token(ciphertext)


def test_decrypt_with_garbage_key_raises() -> None:
    """A non-Fernet key must raise EncryptionError on decrypt."""
    with patch("src.security.encryption.settings") as mock:
        mock.encryption_key = VALID_KEY
        ciphertext = encrypt_token("secret")

    with patch("src.security.encryption.settings") as mock:
        mock.encryption_key = "not-a-valid-fernet-key"
        with pytest.raises(EncryptionError):
            decrypt_token(ciphertext)


def test_encrypt_with_invalid_key_raises() -> None:
    """encrypt_token with a bad key must raise EncryptionError."""
    with patch("src.security.encryption.settings") as mock:
        mock.encryption_key = "totally-invalid"
        with pytest.raises(EncryptionError):
            encrypt_token("anything")


# ── Corrupted ciphertext ──────────────────────────────────────────────────────

def test_decrypt_corrupted_data_raises() -> None:
    with patch("src.security.encryption.settings") as mock:
        mock.encryption_key = VALID_KEY
        with pytest.raises(EncryptionError):
            decrypt_token(b"this-is-not-valid-fernet-data")


def test_decrypt_truncated_ciphertext_raises() -> None:
    with patch("src.security.encryption.settings") as mock:
        mock.encryption_key = VALID_KEY
        ciphertext = encrypt_token("secret")

    with patch("src.security.encryption.settings") as mock:
        mock.encryption_key = VALID_KEY
        with pytest.raises(EncryptionError):
            decrypt_token(ciphertext[:10])
