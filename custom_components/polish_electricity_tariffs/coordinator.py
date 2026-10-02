"""Data coordinator: fetch the static tariff JSON over HTTP."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)


async def async_fetch_json(
    hass: HomeAssistant, url: str
) -> dict[str, Any]:
    """Fetch and parse a JSON document (content-type agnostic)."""
    session = async_get_clientsession(hass)
    async with session.get(url, timeout=REQUEST_TIMEOUT) as resp:
        resp.raise_for_status()
        # GitHub Pages serves JSON as application/octet-stream sometimes,
        # so do not let aiohttp enforce the content type.
        return await resp.json(content_type=None)


async def async_fetch_index(hass: HomeAssistant, base_url: str) -> dict[str, Any]:
    return await async_fetch_json(hass, base_url.rstrip("/") + "/index.json")


async def async_fetch_operator(
    hass: HomeAssistant, base_url: str, file_name: str
) -> dict[str, Any]:
    return await async_fetch_json(hass, base_url.rstrip("/") + "/" + file_name)


class TariffCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Keeps one operator's tariff document fresh."""

    def __init__(
        self,
        hass: HomeAssistant,
        base_url: str,
        operator_id: str,
        file_name: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{operator_id}",
            update_interval=UPDATE_INTERVAL,
        )
        self._base_url = base_url
        self._file_name = file_name
        self.operator_id = operator_id

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await async_fetch_operator(
                self.hass, self._base_url, self._file_name
            )
        except (aiohttp.ClientError, ValueError) as err:
            raise UpdateFailed(f"Nie udało się pobrać danych taryf: {err}") from err
