from cryptography.fernet import Fernet, InvalidToken

from shmuel_backend.config import settings


class EncryptionError(RuntimeError):
    pass


def _fernet() -> Fernet:
    if not settings.encryption_key:
        raise EncryptionError(
            "ENCRYPTION_KEY is not configured. "
            'Generate one: `python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"`'
        )
    return Fernet(settings.encryption_key.encode())


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise EncryptionError(
            "Could not decrypt secret. ENCRYPTION_KEY likely changed."
        ) from exc
