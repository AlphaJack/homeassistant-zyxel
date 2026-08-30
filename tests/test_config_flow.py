"""Offline tests for the Zyxel config flow (client mocked)."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.zyxel.api import ZyxelAuthError
from custom_components.zyxel.const import CONF_SCAN_INTERVAL, DOMAIN

_USER_INPUT = {
    CONF_HOST: "192.168.1.1",
    CONF_USERNAME: "homeassistant",
    CONF_PASSWORD: "secret",
}
_DEVICE = {"SerialNumber": "S220Y14105052", "ModelName": "DX3301-T0"}


async def test_user_flow_creates_entry(hass: HomeAssistant) -> None:
    """A valid submission creates an entry keyed on the serial number."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    with (
        patch(
            "custom_components.zyxel.config_flow._validate", return_value=_DEVICE
        ),
        patch("custom_components.zyxel.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], _USER_INPUT
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Zyxel DX3301-T0"
    assert result["result"].unique_id == "S220Y14105052"
    # Required fields are stored (voluptuous also injects the optional defaults).
    assert result["data"][CONF_HOST] == _USER_INPUT[CONF_HOST]
    assert result["data"][CONF_USERNAME] == _USER_INPUT[CONF_USERNAME]
    assert result["data"][CONF_PASSWORD] == _USER_INPUT[CONF_PASSWORD]


async def test_user_flow_invalid_auth(hass: HomeAssistant) -> None:
    """Bad credentials surface an invalid_auth error on the form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    with patch(
        "custom_components.zyxel.config_flow._validate",
        side_effect=ZyxelAuthError("bad"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], _USER_INPUT
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_reauth_flow_updates_password(hass: HomeAssistant) -> None:
    """Reauth updates the stored credentials and reloads."""
    entry = MockConfigEntry(
        domain=DOMAIN, data=_USER_INPUT, unique_id=_DEVICE["SerialNumber"]
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with (
        patch("custom_components.zyxel.config_flow._validate", return_value=_DEVICE),
        patch("custom_components.zyxel.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "homeassistant", CONF_PASSWORD: "newpass"},
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "newpass"


async def test_options_flow_sets_scan_interval(hass: HomeAssistant) -> None:
    """The options flow stores the scan interval."""
    entry = MockConfigEntry(domain=DOMAIN, data=_USER_INPUT)
    entry.add_to_hass(hass)
    with patch("custom_components.zyxel.async_setup_entry", return_value=True):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] is FlowResultType.FORM
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_SCAN_INTERVAL: 30}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_SCAN_INTERVAL] == 30
