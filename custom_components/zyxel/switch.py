"""Switch platform for the Zyxel integration (Wi-Fi and port-forward control)."""

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
    entities: list[SwitchEntity] = [
        ZyxelWifiRadioSwitch(coordinator, band)
        for band in coordinator.data.get("wifi", {})
    ]
    entities.extend(
        ZyxelSsidSwitch(coordinator, ssid) for ssid in coordinator.data.get("ssids", [])
    )
    entities.extend(
        ZyxelPortForwardSwitch(coordinator, rule)
        for rule in coordinator.data.get("port_forwards", [])
    )
    if coordinator.data.get("led") is not None:
        entities.append(ZyxelLedSwitch(coordinator))
    async_add_entities(entities)


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


class ZyxelSsidSwitch(ZyxelEntity, SwitchEntity):
    """Enable/disable an extra SSID (e.g. a guest network) on one band."""

    _attr_translation_key = "wifi_ssid"
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: ZyxelCoordinator, ssid: dict[str, Any]) -> None:
        """Initialise the SSID switch."""
        super().__init__(coordinator)
        self._index = ssid["index"]
        self._attr_translation_placeholders = {
            "ssid": str(ssid.get("ssid")),
            "band": str(ssid.get("band")),
        }
        # Unused SSID slots stay out of the way until the user enables them.
        self._attr_entity_registry_enabled_default = ssid.get("enabled", False)
        serial = self._data.get("device", {}).get(
            "SerialNumber", coordinator.config_entry.entry_id
        )
        self._attr_unique_id = f"{serial}_ssid_{self._index}"

    def _ssid(self) -> dict[str, Any]:
        for ssid in self.coordinator.data.get("ssids", []):
            if ssid.get("index") == self._index:
                return ssid
        return {}

    @property
    def is_on(self) -> bool:
        """Return True when the SSID is broadcasting."""
        return bool(self._ssid().get("enabled"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the SSID."""
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the SSID."""
        await self._set(False)

    async def _set(self, enabled: bool) -> None:
        await self.coordinator.client.async_set_ssid(self._index, enabled)
        await self.coordinator.async_request_refresh()


class ZyxelPortForwardSwitch(ZyxelEntity, SwitchEntity):
    """Enable/disable one NAT port-forward rule."""

    _attr_translation_key = "port_forward"
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: ZyxelCoordinator, rule: dict[str, Any]) -> None:
        """Initialise the port-forward switch."""
        super().__init__(coordinator)
        self._index = rule["index"]
        self._attr_translation_placeholders = {"name": str(rule.get("name"))}
        serial = self._data.get("device", {}).get(
            "SerialNumber", coordinator.config_entry.entry_id
        )
        self._attr_unique_id = f"{serial}_port_forward_{self._index}"

    def _rule(self) -> dict[str, Any] | None:
        for rule in self.coordinator.data.get("port_forwards", []):
            if rule.get("index") == self._index:
                return rule
        return None

    @property
    def available(self) -> bool:
        """Unavailable once the rule is deleted on the router."""
        return super().available and self._rule() is not None

    @property
    def is_on(self) -> bool:
        """Return True when the rule is active."""
        return bool((self._rule() or {}).get("enabled"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose what the rule forwards."""
        rule = self._rule() or {}
        return {
            key: rule.get(key)
            for key in ("protocol", "external_port", "internal_port", "internal_client")
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the rule."""
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the rule."""
        await self._set(False)

    async def _set(self, enabled: bool) -> None:
        await self.coordinator.client.async_set_port_forward(self._index, enabled)
        await self.coordinator.async_request_refresh()


class ZyxelLedSwitch(ZyxelEntity, SwitchEntity):
    """Turn the router's front-panel LEDs on or off."""

    _attr_translation_key = "led"
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: ZyxelCoordinator) -> None:
        """Initialise the LED switch."""
        super().__init__(coordinator)
        serial = self._data.get("device", {}).get(
            "SerialNumber", coordinator.config_entry.entry_id
        )
        self._attr_unique_id = f"{serial}_led"

    @property
    def is_on(self) -> bool:
        """Return True when the LEDs are on."""
        return bool(self.coordinator.data.get("led"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the LEDs on."""
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the LEDs off."""
        await self._set(False)

    async def _set(self, enabled: bool) -> None:
        await self.coordinator.client.async_set_led(enabled)
        await self.coordinator.async_request_refresh()
