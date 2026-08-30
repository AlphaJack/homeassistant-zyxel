"""Binary sensor platform for the Zyxel integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ZyxelConfigEntry, ZyxelCoordinator
from .entity import ZyxelEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class ZyxelBinaryDescription(BinarySensorEntityDescription):
    """Binary sensor description with a value extractor and capability section."""

    is_on_fn: Callable[[dict[str, Any]], bool]
    section: str


BINARY_SENSORS: tuple[ZyxelBinaryDescription, ...] = (
    ZyxelBinaryDescription(
        key="dsl_link",
        translation_key="dsl_link",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        section="dsl",
        is_on_fn=lambda d: str(d.get("dsl", {}).get("Status")) == "Up",
    ),
    ZyxelBinaryDescription(
        key="cell_link",
        translation_key="cell_link",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        section="cellular",
        is_on_fn=lambda d: str(d.get("cellular", {}).get("INTF_Status")) == "Up",
    ),
)


def _section_present(data: dict[str, Any], section: str) -> bool:
    if section == "dsl":
        return bool(data.get("dsl_all"))
    if section == "cellular":
        return bool(data.get("cellular"))
    return True


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZyxelConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Zyxel binary sensors for whatever the device reports."""
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [
        ZyxelBinarySensor(coordinator, description)
        for description in BINARY_SENSORS
        if _section_present(coordinator.data, description.section)
    ]
    # One registration sensor per enabled VoIP line (FXS models).
    for account in coordinator.data.get("sip", []):
        if account.get("enabled") and account.get("line") is not None:
            entities.append(ZyxelSipBinarySensor(coordinator, account["line"]))
    async_add_entities(entities)


class ZyxelBinarySensor(ZyxelEntity, BinarySensorEntity):
    """A connectivity binary sensor driven by a description."""

    entity_description: ZyxelBinaryDescription

    def __init__(
        self, coordinator: ZyxelCoordinator, description: ZyxelBinaryDescription
    ) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        serial = self._data.get("device", {}).get(
            "SerialNumber", coordinator.config_entry.entry_id
        )
        self._attr_unique_id = f"{serial}_{description.key}"

    @property
    def is_on(self) -> bool:
        """Return True when the link is up."""
        return self.entity_description.is_on_fn(self._data)


class ZyxelSipBinarySensor(ZyxelEntity, BinarySensorEntity):
    """Registration status of a single VoIP (FXS) line."""

    _attr_translation_key = "voip_line"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: ZyxelCoordinator, line: int) -> None:
        """Initialise the VoIP line sensor."""
        super().__init__(coordinator)
        self._line = line
        self._attr_translation_placeholders = {"line": str(line)}
        serial = self._data.get("device", {}).get(
            "SerialNumber", coordinator.config_entry.entry_id
        )
        self._attr_unique_id = f"{serial}_voip_line_{line}"

    def _account(self) -> dict[str, Any]:
        for account in self.coordinator.data.get("sip", []):
            if account.get("line") == self._line:
                return account
        return {}

    @property
    def is_on(self) -> bool:
        """Return True when the line is registered."""
        return bool(self._account().get("registered"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the directory number for context."""
        return {"number": self._account().get("number")}
