from cryptography.fernet import Fernet, InvalidToken

from src.config import settings


class EncryptionError(Exception):
    """Raised when decryption fails due to invalid key or corrupted data."""


def _get_fernet() -> Fernet:
    try:
        return Fernet(settings.encryption_key.encode())
    except (ValueError, Exception) as exc:
        raise EncryptionError(f"Invalid encryption key: {exc}") from exc


def encrypt_token(plaintext: str) -> bytes:
    """Encrypt a plaintext string and return ciphertext bytes."""
    return _get_fernet().encrypt(plaintext.encode())


def decrypt_token(ciphertext: bytes) -> str:
    """Decrypt ciphertext bytes and return the original plaintext string.

    Raises EncryptionError if the key is invalid or the data is corrupted.
    """
    try:
        return _get_fernet().decrypt(ciphertext).decode()
    except InvalidToken as exc:
        raise EncryptionError("Decryption failed: invalid key or corrupted data") from exc
