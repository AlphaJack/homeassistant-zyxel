"""Button platform for the Zyxel integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ZyxelConfigEntry, ZyxelCoordinator
from .entity import ZyxelEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZyxelConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Zyxel reboot button and per-band WPS buttons."""
    coordinator = entry.runtime_data
    entities: list[ButtonEntity] = [ZyxelRebootButton(coordinator)]
    entities.extend(
        ZyxelWpsButton(coordinator, band) for band in coordinator.data.get("wifi", {})
    )
    async_add_entities(entities)


class ZyxelRebootButton(ZyxelEntity, ButtonEntity):
    """Reboots the router."""

    _attr_translation_key = "reboot"
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: ZyxelCoordinator) -> None:
        """Initialise the reboot button."""
        super().__init__(coordinator)
        serial = self._data.get("device", {}).get(
            "SerialNumber", coordinator.config_entry.entry_id
        )
        self._attr_unique_id = f"{serial}_reboot"

    async def async_press(self) -> None:
        """Trigger a reboot."""
        await self.coordinator.client.async_reboot()


class ZyxelWpsButton(ZyxelEntity, ButtonEntity):
    """Starts WPS push-button pairing for a Wi-Fi band."""

    _attr_translation_key = "wps"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: ZyxelCoordinator, band: str) -> None:
        """Initialise the WPS button."""
        super().__init__(coordinator)
        self._band = band
        self._attr_translation_placeholders = {"band": band}
        serial = self._data.get("device", {}).get(
            "SerialNumber", coordinator.config_entry.entry_id
        )
        self._attr_unique_id = f"{serial}_wps_{band}"

    async def async_press(self) -> None:
        """Start WPS pairing on this band."""
        await self.coordinator.client.async_wps_pbc(self._band)
