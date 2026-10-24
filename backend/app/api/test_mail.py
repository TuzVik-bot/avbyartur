"""Read-only access to captured test email; never available to ordinary users."""
import json
from typing import Annotated
from urllib.request import urlopen
from urllib.error import HTTPError

from fastapi import APIRouter, Depends, Response, Path
from app.api.moderation import require_admin
from app.config import get_settings
from app.models import User
from app.services import fail

router = APIRouter(prefix="/api/v1/admin/test-mail", tags=["administration"])


def read_test_mail(path: str):
    # Fixed internal service only. Users cannot choose a host or arbitrary URL.
    try:
        with urlopen(f"http://test-mail:8025/api/v1/{path}", timeout=5) as result:
            data = result.read(1024 * 1024 + 1)
            if len(data) > 1024 * 1024:
                fail(503, "test_mail_unavailable", "Test inbox response is too large")
            return json.loads(data)
    except HTTPError as error:
        if error.code == 404:
            fail(404, "not_found", "Message was not found")
        fail(503, "test_mail_unavailable", "Test inbox is unavailable")
    except (OSError, ValueError):
        fail(503, "test_mail_unavailable", "Test inbox is unavailable")


def enabled(response: Response):
    response.headers["Cache-Control"] = "no-store"
    if not get_settings().test_mail_enabled:
        fail(404, "not_found", "Test inbox is disabled")


@router.get("/messages")
def messages(response: Response, _admin: Annotated[User, Depends(require_admin)]) -> dict:
    enabled(response)
    result = read_test_mail("messages?start=0&limit=30")
    return {"items": [
        {"id": str(item["ID"]), "subject": item.get("Subject", ""),
         "recipients": [entry.get("Address", "") for entry in item.get("To", [])],
         "created_at": item.get("Created", "")}
        for item in result.get("messages", [])
    ]}


@router.get("/messages/{message_id}")
def message(message_id: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{22,64}$")], response: Response, _admin: Annotated[User, Depends(require_admin)]) -> dict:
    enabled(response)
    result = read_test_mail(f"message/{message_id}")
    body = result.get("Text", "")
    return {"id": str(message_id), "subject": result.get("Subject", ""), "body": body[:100000]}
