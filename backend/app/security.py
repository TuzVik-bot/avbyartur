import hashlib
import hmac
import ipaddress
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Request

from app.config import get_settings


_password_hasher = PasswordHasher()
_dummy_password_hash = _password_hasher.hash(secrets.token_urlsafe(24))


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, stored_hash: str | None) -> bool:
    try:
        return _password_hasher.verify(stored_hash or _dummy_password_hash, password) and stored_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def new_secret() -> str:
    return secrets.token_urlsafe(32)


def secret_hash(value: str) -> str:
    key = get_settings().session_secret.get_secret_value().encode()
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def client_ip(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    trusted = []
    for value in get_settings().trusted_proxy_cidrs.split(","):
        value = value.strip()
        if value:
            try:
                trusted.append(ipaddress.ip_network(value, strict=False))
            except ValueError:
                continue
    try:
        peer_address = ipaddress.ip_address(peer)
    except ValueError:
        return peer
    if not any(peer_address in network for network in trusted):
        return peer
    forwarded = request.headers.get("x-forwarded-for", "")
    chain = [item.strip() for item in forwarded.split(",") if item.strip()]
    for candidate in reversed(chain):
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if any(address in network for network in trusted):
            peer = candidate
            continue
        return candidate
    return peer
