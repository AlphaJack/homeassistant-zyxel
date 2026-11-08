"""Tests for session-key handling on DAL writes."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

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
