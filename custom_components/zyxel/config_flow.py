"""Config flow for the Zyxel integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import ZyxelAuthError, ZyxelConnectionError, ZyxelDalClient
from .const import (
    CONF_SCAN_INTERVAL,
    CONF_TRACK_DEVICES,
    CONF_USE_HTTPS,
    CONF_VERIFY_SSL,
    DEFAULT_HOST,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TRACK_DEVICES,
    DEFAULT_USE_HTTPS,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)
from .coordinator import ZyxelConfigEntry


async def _validate(hass: Any, data: Mapping[str, Any]) -> dict[str, Any]:
    """Validate credentials and return the device info."""
    session = async_create_clientsession(
        hass,
        verify_ssl=data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
        cookie_jar=aiohttp.CookieJar(unsafe=True),
    )
    client = ZyxelDalClient(
        session,
        data[CONF_HOST],
        data[CONF_USERNAME],
        data[CONF_PASSWORD],
        use_https=data.get(CONF_USE_HTTPS, DEFAULT_USE_HTTPS),
        verify_ssl=data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
    )
    try:
        await client.login()
        status = await client.async_get_status()
    finally:
        await client.logout()
    return status.get("device", {})


class ZyxelConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the Zyxel config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                device = await _validate(self.hass, user_input)
            except ZyxelAuthError:
                errors["base"] = "invalid_auth"
            except ZyxelConnectionError:
                errors["base"] = "cannot_connect"
            else:
                serial = device.get("SerialNumber")
                if serial:
                    await self.async_set_unique_id(serial)
                    self._abort_if_unique_id_configured()
                model = device.get("ModelName", "Router")
                return self.async_create_entry(
                    title=f"Zyxel {model}", data=user_input
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Optional(CONF_USE_HTTPS, default=DEFAULT_USE_HTTPS): bool,
                    vol.Optional(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL): bool,
                    vol.Optional(
                        CONF_TRACK_DEVICES, default=DEFAULT_TRACK_DEVICES
                    ): bool,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication when credentials fail."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm re-authentication."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()
        if user_input is not None:
            data = {**reauth_entry.data, **user_input}
            try:
                await _validate(self.hass, data)
            except ZyxelAuthError:
                errors["base"] = "invalid_auth"
            except ZyxelConnectionError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(reauth_entry, data=data)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USERNAME,
                        default=reauth_entry.data.get(CONF_USERNAME),
                    ): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ZyxelConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return ZyxelOptionsFlow()


class ZyxelOptionsFlow(OptionsFlow):
    """Handle Zyxel options (scan interval)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        entry = self.config_entry
        current_interval = entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        current_track = entry.options.get(
            CONF_TRACK_DEVICES,
            entry.data.get(CONF_TRACK_DEVICES, DEFAULT_TRACK_DEVICES),
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL, default=current_interval
                    ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL)),
                    vol.Optional(CONF_TRACK_DEVICES, default=current_track): bool,
                }
            ),
        )
