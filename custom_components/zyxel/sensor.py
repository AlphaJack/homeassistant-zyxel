"""Sensor platform for the Zyxel integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfDataRate,
    UnitOfInformation,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util
from homeassistant.util.variance import ignore_variance

from .coordinator import ZyxelConfigEntry, ZyxelCoordinator
from .entity import ZyxelEntity

PARALLEL_UPDATES = 0  # the coordinator owns all polling

# The LAN bridge is the reliably-named interface for whole-house throughput;
# WAN-side interface naming varies by connection mode.
_TRAFFIC_IFACE = "br0"


@dataclass(frozen=True, kw_only=True)
class ZyxelSensorDescription(SensorEntityDescription):
    """Sensor description with a value extractor and a capability section."""

    value_fn: Callable[[dict[str, Any]], StateType]
    # Which device capability this sensor belongs to; the platform only creates
    # it when the router actually reports that section.
    section: str = "common"


def _section_present(data: dict[str, Any], section: str) -> bool:
    """Return whether the router exposes the data a section needs."""
    if section == "dsl":
        return bool(data.get("dsl_all"))
    if section == "cellular":
        return bool(data.get("cellular"))
    if section == "traffic":
        return _TRAFFIC_IFACE in data.get("traffic", {})
    if section == "wan":
        return bool(data.get("wan", {}).get("ip"))
    return True  # "common"


def _cell(key: str) -> Callable[[dict[str, Any]], StateType]:
    def _fn(data: dict[str, Any]) -> StateType:
        return data.get("cellular", {}).get(key)

    return _fn


def _memory_used_percent(data: dict[str, Any]) -> StateType:
    system = data.get("system", {})
    total = system.get("Total")
    free = system.get("Free")
    if not total:
        return None
    return round((total - free) / total * 100, 1)


def _traffic(direction: str) -> Callable[[dict[str, Any]], StateType]:
    def _fn(data: dict[str, Any]) -> StateType:
        return data.get("traffic", {}).get(_TRAFFIC_IFACE, {}).get(direction)

    return _fn


SENSORS: tuple[ZyxelSensorDescription, ...] = (
    ZyxelSensorDescription(
        key="dsl_downstream_rate",
        translation_key="dsl_downstream_rate",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.KILOBITS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("dsl", {}).get("DownstreamCurrRate"),
        section="dsl",
    ),
    ZyxelSensorDescription(
        key="dsl_upstream_rate",
        translation_key="dsl_upstream_rate",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.KILOBITS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("dsl", {}).get("UpstreamCurrRate"),
        section="dsl",
    ),
    ZyxelSensorDescription(
        key="dsl_status",
        translation_key="dsl_status",
        device_class=SensorDeviceClass.ENUM,
        options=["Up", "Down", "NoSignal", "Initializing", "EstablishingLink"],
        value_fn=lambda d: d.get("dsl", {}).get("Status"),
        section="dsl",
    ),
    ZyxelSensorDescription(
        key="cpu_usage",
        translation_key="cpu_usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("system", {}).get("CPUUsage"),
    ),
    ZyxelSensorDescription(
        key="memory_used",
        translation_key="memory_used",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_memory_used_percent,
    ),
    ZyxelSensorDescription(
        key="firmware_version",
        translation_key="firmware_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("device", {}).get("SoftwareVersion"),
    ),
    ZyxelSensorDescription(
        key="wan_ip",
        translation_key="wan_ip",
        entity_category=EntityCategory.DIAGNOSTIC,
        section="wan",
        value_fn=lambda d: d.get("wan", {}).get("ip"),
    ),
    ZyxelSensorDescription(
        key="connected_clients",
        translation_key="connected_clients",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: sum(1 for h in d.get("hosts", []) if h.get("active")),
    ),
    ZyxelSensorDescription(
        key="lan_bytes_received",
        translation_key="lan_bytes_received",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        value_fn=_traffic("BytesReceived"),
        section="traffic",
    ),
    ZyxelSensorDescription(
        key="lan_bytes_sent",
        translation_key="lan_bytes_sent",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        value_fn=_traffic("BytesSent"),
        section="traffic",
    ),
    # --- Cellular / 5G (folded in from the nr7101 / ha-zyxel field mapping) ---
    ZyxelSensorDescription(
        key="cell_rssi",
        translation_key="cell_rssi",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        section="cellular",
        value_fn=_cell("INTF_RSSI"),
    ),
    ZyxelSensorDescription(
        key="cell_rsrp",
        translation_key="cell_rsrp",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        section="cellular",
        value_fn=_cell("INTF_RSRP"),
    ),
    ZyxelSensorDescription(
        key="cell_rsrq",
        translation_key="cell_rsrq",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS,
        state_class=SensorStateClass.MEASUREMENT,
        section="cellular",
        value_fn=_cell("INTF_RSRQ"),
    ),
    ZyxelSensorDescription(
        key="cell_sinr",
        translation_key="cell_sinr",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS,
        state_class=SensorStateClass.MEASUREMENT,
        section="cellular",
        value_fn=_cell("INTF_SINR"),
    ),
    ZyxelSensorDescription(
        key="cell_band",
        translation_key="cell_band",
        section="cellular",
        value_fn=_cell("INTF_Current_Band"),
    ),
    ZyxelSensorDescription(
        key="cell_access_technology",
        translation_key="cell_access_technology",
        section="cellular",
        value_fn=_cell("INTF_Current_Access_Technology"),
    ),
    ZyxelSensorDescription(
        key="cell_id",
        translation_key="cell_id",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        section="cellular",
        value_fn=_cell("INTF_Cell_ID"),
    ),
    ZyxelSensorDescription(
        key="cell_physical_id",
        translation_key="cell_physical_id",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        section="cellular",
        value_fn=_cell("INTF_PhyCell_ID"),
    ),
    ZyxelSensorDescription(
        key="cell_nsa_rsrp",
        translation_key="cell_nsa_rsrp",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        section="cellular",
        value_fn=_cell("NSA_RSRP"),
    ),
    ZyxelSensorDescription(
        key="cell_nsa_sinr",
        translation_key="cell_nsa_sinr",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        section="cellular",
        value_fn=_cell("NSA_SINR"),
    ),
    ZyxelSensorDescription(
        key="cell_temperature",
        translation_key="cell_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        section="cellular",
        value_fn=_cell("X_ZYXEL_TEMPERATURE_AMBIENT"),
    ),
)

# Cellular keys already covered by a curated sensor above; everything else the
# router reports under cellwan_status is offered as a disabled diagnostic sensor
# (mirrors "unknown fields become disabled diagnostics").
_CURATED_CELL_KEYS = {
    "INTF_RSSI",
    "INTF_RSRP",
    "INTF_RSRQ",
    "INTF_SINR",
    "INTF_Current_Band",
    "INTF_Current_Access_Technology",
    "INTF_Cell_ID",
    "INTF_PhyCell_ID",
    "NSA_RSRP",
    "NSA_SINR",
    "X_ZYXEL_TEMPERATURE_AMBIENT",
    "INTF_Status",  # exposed as a binary_sensor instead
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZyxelConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Zyxel sensors for whatever the device reports."""
    coordinator = entry.runtime_data
    data = coordinator.data

    entities: list[SensorEntity] = [
        ZyxelSensor(coordinator, description)
        for description in SENSORS
        if _section_present(data, description.section)
    ]
    entities.append(ZyxelUptimeSensor(coordinator))

    # Any additional cellular field the router reports becomes a disabled
    # diagnostic sensor, so a cellular model is fully covered even where a
    # curated sensor does not exist.
    for key, value in (data.get("cellular") or {}).items():
        if key in _CURATED_CELL_KEYS:
            continue
        if isinstance(value, (str, int, float, bool)):
            entities.append(ZyxelGenericCellSensor(coordinator, key))

    async_add_entities(entities)


class ZyxelSensor(ZyxelEntity, SensorEntity):
    """A value sensor driven by a description's value_fn."""

    entity_description: ZyxelSensorDescription

    def __init__(
        self, coordinator: ZyxelCoordinator, description: ZyxelSensorDescription
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        serial = self._data.get("device", {}).get(
            "SerialNumber", coordinator.config_entry.entry_id
        )
        self._attr_unique_id = f"{serial}_{description.key}"

    @property
    def native_value(self) -> StateType:
        """Return the sensor value."""
        return self.entity_description.value_fn(self._data)


class ZyxelGenericCellSensor(ZyxelEntity, SensorEntity):
    """Disabled-by-default diagnostic sensor for an unmapped cellular field."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: ZyxelCoordinator, key: str) -> None:
        """Initialise a generic cellular sensor."""
        super().__init__(coordinator)
        self._key = key
        serial = self._data.get("device", {}).get(
            "SerialNumber", coordinator.config_entry.entry_id
        )
        self._attr_unique_id = f"{serial}_cell_{key}"
        self._attr_name = key.removeprefix("X_ZYXEL_").replace("_", " ").capitalize()

    @property
    def native_value(self) -> StateType:
        """Return the raw cellular field value."""
        return self.coordinator.data.get("cellular", {}).get(self._key)


class ZyxelUptimeSensor(ZyxelEntity, SensorEntity):
    """Boot time as a timestamp, stabilised against per-poll jitter.

    Uses the same ``ignore_variance`` helper the core Starlink integration uses
    for uptime, so the reported boot time only shifts when it drifts by more
    than a minute (avoids churning the state on every poll).
    """

    _attr_translation_key = "uptime"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: ZyxelCoordinator) -> None:
        """Initialise the uptime sensor."""
        super().__init__(coordinator)
        serial = self._data.get("device", {}).get(
            "SerialNumber", coordinator.config_entry.entry_id
        )
        self._attr_unique_id = f"{serial}_uptime"
        self._stabilize = ignore_variance(
            lambda seconds: dt_util.utcnow() - timedelta(seconds=int(seconds)),
            timedelta(minutes=1),
        )

    @property
    def native_value(self) -> datetime | None:
        """Return the (stabilised) boot timestamp."""
        uptime = self._data.get("device", {}).get("UpTime")
        if not uptime:
            return None
        return self._stabilize(uptime)
