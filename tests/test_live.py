"""Live end-to-end test against a real Zyxel router.

Skipped unless ZYXEL_HOST / ZYXEL_USER / ZYXEL_PASS are set in the environment.
It loads the integration exactly as Home Assistant would (config entry ->
coordinator -> platforms) and asserts that real entities are produced.
"""

from __future__ import annotations

import asyncio
import os

import aiohttp
import pytest
import pytest_socket
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.zyxel.api import ZyxelConnectionError, ZyxelDalClient
from custom_components.zyxel.const import CONF_USE_HTTPS, CONF_VERIFY_SSL, DOMAIN

HOST = os.environ.get("ZYXEL_HOST")
USER = os.environ.get("ZYXEL_USER")
PASSWORD = os.environ.get("ZYXEL_PASS")

pytestmark = pytest.mark.skipif(
    not (HOST and USER and PASSWORD),
    reason="Live router credentials (ZYXEL_HOST/USER/PASS) not provided",
)


async def _wait_for_free_session(attempts: int = 6, delay: int = 15) -> bool:
    """Return True once a login succeeds (session slot free)."""
    for attempt in range(attempts):
        session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True))
        client = ZyxelDalClient(session, HOST, USER, PASSWORD)
        try:
            await client.login()
            await client.logout()
            return True
        except ZyxelConnectionError:
            if attempt < attempts - 1:
                await asyncio.sleep(delay)
        finally:
            await session.close()
    return False


async def test_live_setup_creates_entities(hass: HomeAssistant) -> None:
    """The integration sets up and produces sensors from a real router."""
    # The HA test harness blocks network access; permit the router for this
    # live test only.
    pytest_socket.enable_socket()
    pytest_socket.socket_allow_hosts([HOST, "127.0.0.1"], allow_unix_socket=True)

    # The router allows one session per user; a lingering session from a prior
    # run frees within its idle timeout. Wait for a free slot, else skip.
    if not await _wait_for_free_session():
        pytest.skip("Router session persistently locked (single-session limit)")

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: HOST,
            CONF_USERNAME: USER,
            CONF_PASSWORD: PASSWORD,
            CONF_USE_HTTPS: os.environ.get("ZYXEL_HTTPS") == "1",
            CONF_VERIFY_SSL: False,
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = entry.runtime_data
    assert coordinator.last_update_success
    assert coordinator.data["device"].get("ModelName")

    states = hass.states.async_all()
    entity_ids = sorted(s.entity_id for s in states)
    print("\n--- entity states ---")
    for state in sorted(states, key=lambda s: s.entity_id):
        print(f"{state.entity_id} = {state.state}")

    # DSL downstream rate must exist and be a positive number.
    downstream = next(
        (s for s in states if s.entity_id.endswith("_dsl_downstream_rate")), None
    )
    assert downstream is not None, entity_ids
    assert float(downstream.state) > 0

    # Core platforms are represented.
    assert any(e.startswith("sensor.") for e in entity_ids)
    assert any(e.startswith("binary_sensor.") for e in entity_ids)
    assert any(e.startswith("button.") for e in entity_ids)
    # Wi-Fi radio switch(es) built from the real wlan objects.
    assert any(e.startswith("switch.") for e in entity_ids), entity_ids

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
