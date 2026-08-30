"""DataUpdateCoordinator for the Zyxel integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ZyxelAuthError, ZyxelConnectionError, ZyxelDalClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

type ZyxelConfigEntry = ConfigEntry[ZyxelCoordinator]


class ZyxelCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls the router and shares one snapshot across all platforms."""

    config_entry: ZyxelConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ZyxelConfigEntry,
        client: ZyxelDalClient,
        update_interval: timedelta,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=update_interval,
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch the latest status from the router."""
        try:
            async with asyncio.timeout(30):
                return await self.client.async_get_status()
        except ZyxelAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except ZyxelConnectionError as err:
            raise UpdateFailed(str(err)) from err
