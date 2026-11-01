"""Validate public messenger links before storing or revealing them."""

import re
from urllib.parse import urlsplit


def normalize_contact_url(value: str, channel: str) -> str:
    value = value.strip()
    if len(value) > 320 or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("Invalid messenger link")
    try:
        url = urlsplit(value)
        if url.scheme.lower() != "https" or not url.hostname or url.username is not None or url.password is not None or url.port is not None or url.query or url.fragment:
            raise ValueError("Invalid messenger link")
    except ValueError:
        raise ValueError("Invalid messenger link") from None
    host = url.hostname.lower()
    parts = [part for part in url.path.split("/") if part]
    if len(parts) != 1:
        raise ValueError("Invalid messenger link")
    if channel == "telegram":
        valid = host in {"t.me", "telegram.me"} and re.fullmatch(r"[A-Za-z0-9_]{5,32}", parts[0])
    elif channel == "viber":
        valid = host in {"viber.me", "viber.com", "www.viber.com"} and re.fullmatch(r"[A-Za-z0-9_.+-]{1,160}", parts[0])
    else:
        valid = False
    if not valid:
        raise ValueError("Invalid messenger link")
    return f"https://{host}/{parts[0]}"


def validated_contact_channels(telegram: str | None, viber: str | None) -> list[dict]:
    channels = []
    for channel, value in (("telegram", telegram), ("viber", viber)):
        if value:
            try:
                uri = normalize_contact_url(value, channel)
            except ValueError:
                continue
            channels.append({"channel": channel, "uri": uri, "opted_in": True})
    return channels
