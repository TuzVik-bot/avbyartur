import hashlib
import hmac
import ipaddress
import logging
import secrets
import time
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.logging_config import log_event
from app.models import RateLimitBucket


# Child of the API JSON logger so the warning is emitted as a structured event.
logger = logging.getLogger("avtorinok.api.security")

# A client IP inside TRUSTED_PROXY_CIDRS means the real address was lost
# upstream; IP limits then become a coarse site-wide cap (limit * factor).
UNKNOWN_CLIENT_IP_LIMIT_FACTOR = 20
UNRESOLVED_IP_WARNING_INTERVAL_SECONDS = 300
_last_unresolved_ip_warning = 0.0

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


def _trusted_proxy_networks() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    networks = []
    for value in get_settings().trusted_proxy_cidrs.split(","):
        value = value.strip()
        if value:
            try:
                networks.append(ipaddress.ip_network(value, strict=False))
            except ValueError:
                continue
    return networks


def client_ip(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    trusted = _trusted_proxy_networks()
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


def client_ip_is_trusted_proxy(ip: str) -> bool:
    """True when the resolved client IP is one of our own proxies, i.e. the real client is unknown."""

    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(address in network for network in _trusted_proxy_networks())


def _warn_unresolved_client_ip() -> None:
    global _last_unresolved_ip_warning
    now = time.monotonic()
    if now - _last_unresolved_ip_warning < UNRESOLVED_IP_WARNING_INTERVAL_SECONDS:
        return
    _last_unresolved_ip_warning = now
    log_event(logger, logging.WARNING, "client_ip_unresolved")


def ip_scoped_limit(ip: str, limit: int) -> int:
    """Threshold for a per-IP rate limit; widened to a site-wide cap when the client IP is unknown."""

    if not client_ip_is_trusted_proxy(ip):
        return limit
    _warn_unresolved_client_ip()
    return limit * UNKNOWN_CLIENT_IP_LIMIT_FACTOR


def rate_limit_key(namespace: str, subject: str) -> str:
    # Must match the bucket key used by app.services.consume_rate_limit.
    return hashlib.sha256(f"{namespace}:{subject}".encode()).hexdigest()


def rate_limit_exhausted(db: Session, namespace: str, subject: str, limit: int, period: timedelta) -> bool:
    """Return True when the current window already holds `limit` hits, without consuming one."""

    cutoff = datetime.now(timezone.utc) - period
    count = db.scalar(
        select(RateLimitBucket.count).where(
            RateLimitBucket.key_hash == rate_limit_key(namespace, subject),
            RateLimitBucket.window_started >= cutoff,
        )
    )
    return count is not None and count >= limit
