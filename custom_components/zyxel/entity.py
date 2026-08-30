"""Base entity for the Zyxel integration."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import ZyxelCoordinator


class ZyxelEntity(CoordinatorEntity[ZyxelCoordinator]):
    """Base class wiring every entity to the shared router device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ZyxelCoordinator) -> None:
        """Initialise the base entity."""
        super().__init__(coordinator)
        device = coordinator.data.get("device", {})
        serial = device.get("SerialNumber") or coordinator.config_entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            manufacturer=MANUFACTURER,
            model=device.get("ModelName"),
            name=f"Zyxel {device.get('ModelName', 'Router')}",
            sw_version=device.get("SoftwareVersion"),
            serial_number=serial,
            configuration_url=coordinator.client.base_url,
        )

    @property
    def _data(self) -> dict[str, Any]:
        return self.coordinator.data
