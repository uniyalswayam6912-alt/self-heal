import os

from cryptography.fernet import Fernet


ENCRYPTION_KEY = os.getenv("INTEGRATION_ENCRYPTION_KEY")

if not ENCRYPTION_KEY:
    raise RuntimeError(
        "INTEGRATION_ENCRYPTION_KEY environment variable is not configured"
    )

fernet = Fernet(ENCRYPTION_KEY.encode())


def encrypt_credential(value: str) -> str:
    return fernet.encrypt(value.encode()).decode()


def decrypt_credential(value: str) -> str:
    return fernet.decrypt(value.encode()).decode()