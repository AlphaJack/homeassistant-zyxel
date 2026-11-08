"""Tests for the write-capable controls (Wi-Fi switch, WPS + reboot buttons)."""

from __future__ import annotations

from contextlib import ExitStack
from typing import Any
from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.zyxel.const import DOMAIN

SNAPSHOT: dict[str, Any] = {
    "device": {"SerialNumber": "DX1", "ModelName": "DX3301-T0", "UpTime": 1},
    "system": {"CPUUsage": 5, "Total": 100, "Free": 50},
    "dsl": {"Status": "Up", "DownstreamCurrRate": 1},
    "dsl_all": [{"Status": "Up"}],
    "cellular": {},
    "wan": {},
    "sip": [],
    "wifi": {
        "2.4GHz": {"radio": True, "ssid": "Home"},
        "5GHz": {"radio": True, "ssid": "Home-5"},
    },
    "ssids": [
        {"index": 2, "band": "2.4GHz", "ssid": "Guest", "enabled": True},
        {"index": 3, "band": "2.4GHz", "ssid": "Unused", "enabled": False},
    ],
    "port_forwards": [
        {"index": 4, "name": "Web", "enabled": True, "protocol": "TCP"},
    ],
    "traffic": {},
    "hosts": [],
}


def _mock_client(stack: ExitStack) -> dict[str, AsyncMock]:
    """Patch every network method of the client; return the write mocks."""
    mocks = {
        "async_set_wifi_radio": AsyncMock(),
        "async_wps_pbc": AsyncMock(),
        "async_set_ssid": AsyncMock(),
        "async_set_port_forward": AsyncMock(),
        "async_set_led": AsyncMock(),
        "async_reboot": AsyncMock(),
    }
    stack.enter_context(
        patch("custom_components.zyxel.api.ZyxelDalClient.login", new=AsyncMock())
    )
    stack.enter_context(
        patch("custom_components.zyxel.api.ZyxelDalClient.logout", new=AsyncMock())
    )
    stack.enter_context(
        patch(
            "custom_components.zyxel.api.ZyxelDalClient.async_get_status",
            new=AsyncMock(return_value=SNAPSHOT),
        )
    )
    for name, mock in mocks.items():
        stack.enter_context(
            patch(f"custom_components.zyxel.api.ZyxelDalClient.{name}", new=mock)
        )
    return mocks


async def _add_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: "192.168.1.1",
            CONF_USERNAME: "homeassistant",
            CONF_PASSWORD: "secret",
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _uid_to_entity(hass: HomeAssistant, entry: MockConfigEntry, uid: str) -> str:
    reg = er.async_get(hass)
    return next(
        e.entity_id
        for e in er.async_entries_for_config_entry(reg, entry.entry_id)
        if e.unique_id == uid
    )


async def test_controls_created(hass: HomeAssistant) -> None:
    """A Wi-Fi switch and WPS button exist for each band, plus reboot."""
    with ExitStack() as stack:
        _mock_client(stack)
        entry = await _add_entry(hass)
        reg = er.async_get(hass)
        uids = {
            e.unique_id for e in er.async_entries_for_config_entry(reg, entry.entry_id)
        }
    assert {"DX1_wifi_2.4GHz", "DX1_wifi_5GHz", "DX1_wps_2.4GHz", "DX1_reboot"} <= uids


async def test_wifi_switch_calls_api(hass: HomeAssistant) -> None:
    """Turning a Wi-Fi switch off calls the radio setter with the band."""
    with ExitStack() as stack:
        mocks = _mock_client(stack)
        entry = await _add_entry(hass)
        entity_id = _uid_to_entity(hass, entry, "DX1_wifi_5GHz")
        await hass.services.async_call(
            "switch", "turn_off", {"entity_id": entity_id}, blocking=True
        )
    mocks["async_set_wifi_radio"].assert_awaited_once_with("5GHz", False)


async def test_wps_button_calls_api(hass: HomeAssistant) -> None:
    """Pressing a WPS button starts pairing on that band."""
    with ExitStack() as stack:
        mocks = _mock_client(stack)
        entry = await _add_entry(hass)
        entity_id = _uid_to_entity(hass, entry, "DX1_wps_2.4GHz")
        await hass.services.async_call(
            "button", "press", {"entity_id": entity_id}, blocking=True
        )
    mocks["async_wps_pbc"].assert_awaited_once_with("2.4GHz")


async def test_ssid_switch_calls_api(hass: HomeAssistant) -> None:
    """Turning a guest SSID off calls the SSID setter with its index."""
    with ExitStack() as stack:
        mocks = _mock_client(stack)
        entry = await _add_entry(hass)
        entity_id = _uid_to_entity(hass, entry, "DX1_ssid_2")
        await hass.services.async_call(
            "switch", "turn_off", {"entity_id": entity_id}, blocking=True
        )
    mocks["async_set_ssid"].assert_awaited_once_with(2, False)


async def test_unused_ssid_switch_disabled_by_default(hass: HomeAssistant) -> None:
    """An SSID slot that is off starts as a disabled entity."""
    with ExitStack() as stack:
        _mock_client(stack)
        entry = await _add_entry(hass)
        reg = er.async_get(hass)
        entity = reg.async_get(_uid_to_entity(hass, entry, "DX1_ssid_3"))
    assert entity.disabled_by is er.RegistryEntryDisabler.INTEGRATION


async def test_port_forward_switch_calls_api(hass: HomeAssistant) -> None:
    """Turning a port-forward switch off calls the setter with the rule index."""
    with ExitStack() as stack:
        mocks = _mock_client(stack)
        entry = await _add_entry(hass)
        entity_id = _uid_to_entity(hass, entry, "DX1_port_forward_4")
        await hass.services.async_call(
            "switch", "turn_off", {"entity_id": entity_id}, blocking=True
        )
    mocks["async_set_port_forward"].assert_awaited_once_with(4, False)


async def test_led_switch_only_when_supported(hass: HomeAssistant) -> None:
    """Without LED state in the snapshot there is no LED switch."""
    with ExitStack() as stack:
        _mock_client(stack)
        entry = await _add_entry(hass)
        reg = er.async_get(hass)
        uids = {
            e.unique_id for e in er.async_entries_for_config_entry(reg, entry.entry_id)
        }
    assert "DX1_led" not in uids


async def test_led_switch_calls_api(hass: HomeAssistant) -> None:
    """With LED state reported, the switch turns the LEDs off."""
    SNAPSHOT["led"] = True
    try:
        with ExitStack() as stack:
            mocks = _mock_client(stack)
            entry = await _add_entry(hass)
            entity_id = _uid_to_entity(hass, entry, "DX1_led")
            await hass.services.async_call(
                "switch", "turn_off", {"entity_id": entity_id}, blocking=True
            )
    finally:
        SNAPSHOT.pop("led")
    mocks["async_set_led"].assert_awaited_once_with(False)
