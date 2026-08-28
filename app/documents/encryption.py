from cryptography.fernet import Fernet
from django.conf import settings

_fernet = Fernet(settings.VAULT_ENCRYPTION_KEY.encode())


def encrypt_bytes(data: bytes) -> bytes:
    return _fernet.encrypt(data)


def decrypt_bytes(token: bytes) -> bytes:
    return _fernet.decrypt(token)
