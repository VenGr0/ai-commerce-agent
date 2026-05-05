import base64
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.fernet import Fernet
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload: dict[str, Any] = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def decode_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        subject = payload.get("sub")
        return str(subject) if subject else None
    except JWTError:
        return None


def _derived_fernet_key() -> bytes:
    if settings.FERNET_KEY:
        return settings.FERNET_KEY.encode()
    digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return base64.urlsafe_b64encode(digest)


fernet = Fernet(_derived_fernet_key())


def encrypt_secret(value: str) -> str:
    return fernet.encrypt(value.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    return fernet.decrypt(ciphertext.encode()).decode()
