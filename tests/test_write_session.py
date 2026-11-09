"""Tests for session-key handling on DAL writes."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from custom_components.zyxel.api import ZyxelConnectionError, ZyxelDalClient


class _FakeResponse:
    def __init__(self, status: int, body: Any = None, error: Exception | None = None):
        self.status = status
        self._body = body
        self._error = error

    async def __aenter__(self) -> _FakeResponse:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    def raise_for_status(self) -> None:
        return None

    async def json(self, content_type: str | None = None) -> Any:
        if self._error:
            raise self._error
        return self._body


def _client(response: _FakeResponse) -> ZyxelDalClient:
    session = MagicMock()
    session.request = MagicMock(return_value=response)
    client = ZyxelDalClient(session, "router.test", "user", "pw")
    client.sessionkey = "old"
    return client


async def test_write_rotates_session_key() -> None:
    client = _client(
        _FakeResponse(200, {"result": "ZCFG_SUCCESS", "sessionkey": "new"})
    )
    await client.async_dal_write("wps", {"Band": "5GHz"})
    assert client.sessionkey == "new"


async def test_write_403_drops_session_key() -> None:
    client = _client(_FakeResponse(403))
    with pytest.raises(ZyxelConnectionError):
        await client.async_dal_write("wps", {"Band": "5GHz"})
    assert client.sessionkey is None


async def test_write_unreadable_reply_drops_session_key() -> None:
    client = _client(_FakeResponse(200, error=ValueError("empty body")))
    with pytest.raises(ZyxelConnectionError):
        await client.async_dal_write("wps", {"Band": "5GHz"})
    assert client.sessionkey is None


async def test_operations_are_serialized() -> None:
    client = _client(_FakeResponse(200, {"result": "ZCFG_SUCCESS"}))
    events: list[str] = []
    poll_started = asyncio.Event()
    release_poll = asyncio.Event()

    async def slow_get_objects(oid: str) -> list[dict[str, Any]]:
        if oid == "status":
            events.append("poll-start")
            poll_started.set()
            await release_poll.wait()
            events.append("poll-end")
            return []
        events.append("write-read")
        return [{"Band": "5GHz"}]

    async def first_object(oid: str) -> Any:
        objects = await slow_get_objects(oid)
        return objects[0] if objects else None

    client.get_objects = slow_get_objects  # type: ignore[method-assign]
    client.get_object = first_object  # type: ignore[method-assign]
    client._get_optional = AsyncMock(return_value=None)  # type: ignore[method-assign]
    client._get_optional_list = AsyncMock(return_value=[])  # type: ignore[method-assign]
    client._get_led = AsyncMock(return_value=None)  # type: ignore[method-assign]

    poll = asyncio.create_task(client.async_get_status())
    await asyncio.wait_for(poll_started.wait(), 5)
    write = asyncio.create_task(client.async_wps_pbc("5GHz"))
    await asyncio.sleep(0)
    assert events == ["poll-start"]
    release_poll.set()
    await asyncio.wait_for(asyncio.gather(poll, write), 5)
    assert events == ["poll-start", "poll-end", "write-read"]


class _ErrorResponse(_FakeResponse):
    def raise_for_status(self) -> None:
        raise aiohttp.ClientResponseError(
            MagicMock(real_url="http://router.test/cgi-bin/Reboot?sessionkey=old"),
            (),
            status=self.status,
        )


async def test_http_error_message_omits_session_key() -> None:
    session = MagicMock()
    session.get = MagicMock(return_value=_ErrorResponse(500))
    session.post = MagicMock(return_value=_ErrorResponse(500))
    client = ZyxelDalClient(session, "router.test", "user", "pw")
    client.sessionkey = "old"
    with pytest.raises(ZyxelConnectionError) as get_err:
        await client._dal_get("status")
    with pytest.raises(ZyxelConnectionError) as reboot_err:
        await client.async_reboot()
    for err in (get_err.value, reboot_err.value):
        assert str(err) == "HTTP 500"
        assert err.__cause__ is None
