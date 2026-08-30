"""Switch platform for the Zyxel integration (Wi-Fi radio control)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ZyxelConfigEntry, ZyxelCoordinator
from .entity import ZyxelEntity

PARALLEL_UPDATES = 1  # serialise writes to the single-session router


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZyxelConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up a Wi-Fi radio switch per band the device reports."""
    coordinator = entry.runtime_data
    async_add_entities(
        ZyxelWifiRadioSwitch(coordinator, band)
        for band in coordinator.data.get("wifi", {})
    )


class ZyxelWifiRadioSwitch(ZyxelEntity, SwitchEntity):
    """Enable/disable a Wi-Fi band's radio."""

    _attr_translation_key = "wifi_radio"
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: ZyxelCoordinator, band: str) -> None:
        """Initialise the Wi-Fi radio switch."""
        super().__init__(coordinator)
        self._band = band
        self._attr_translation_placeholders = {"band": band}
        serial = self._data.get("device", {}).get(
            "SerialNumber", coordinator.config_entry.entry_id
        )
        self._attr_unique_id = f"{serial}_wifi_{band}"

    def _band_state(self) -> dict[str, Any]:
        return self.coordinator.data.get("wifi", {}).get(self._band, {})

    @property
    def is_on(self) -> bool:
        """Return True when the radio is enabled."""
        return bool(self._band_state().get("radio"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the SSID for context."""
        return {"ssid": self._band_state().get("ssid")}

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the radio on."""
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the radio off."""
        await self._set(False)

    async def _set(self, enabled: bool) -> None:
        await self.coordinator.client.async_set_wifi_radio(self._band, enabled)
        await self.coordinator.async_request_refresh()
