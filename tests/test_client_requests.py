"""Run the real client request path against a fake, unencrypted router."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from custom_components.zyxel.api import ZyxelDalClient


class _Resp:
    def __init__(self, body: Any) -> None:
        self.status = 200
        self._body = body

    async def __aenter__(self) -> _Resp:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    def raise_for_status(self) -> None:
        return None

    async def json(self, content_type: str | None = None) -> Any:
        return self._body


def _route(url: str) -> Any:
    if "LEDStatus" in url:
        return {"isactive": True}
    if "oid=status" in url:
        return {
            "result": "ZCFG_SUCCESS",
            "Object": [{"DeviceInfo": {"ModelName": "X"}}],
        }
    return {"result": "ZCFG_SUCCESS", "Object": []}


async def test_get_status_runs_every_request() -> None:
    """Every GET goes through aiohttp with one merged headers mapping."""
    calls: list[dict[str, Any]] = []

    def fake_get(url: str, **kwargs: Any) -> _Resp:
        calls.append({"url": url, **kwargs})
        return _Resp(_route(url))

    session = MagicMock()
    session.get = fake_get
    client = ZyxelDalClient(session, "router.test", "user", "pw")
    client.sessionkey = "key"

    status = await client.async_get_status()

    assert status["device"] == {"ModelName": "X"}
    assert status["led"] is True
    led_call = next(c for c in calls if "LEDStatus" in c["url"])
    assert led_call["headers"]["CSRFToken"] == "key"
    assert all("headers" in c for c in calls)
