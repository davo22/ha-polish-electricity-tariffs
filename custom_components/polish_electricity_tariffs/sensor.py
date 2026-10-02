"""Sensors exposing current electricity prices."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    ATTRIBUTION,
    CONF_ENERGY_OVERRIDE,
    CONF_INCLUDE_VAT,
    CONF_OPERATOR,
    CONF_PHASE,
    CONF_PRODUCT,
    CONF_TARIFF,
    DEFAULT_INCLUDE_VAT,
    DOMAIN,
)
from .coordinator import TariffCoordinator
from . import pricing

UNIT = "PLN/kWh"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: TariffCoordinator = hass.data[DOMAIN][entry.entry_id]
    group = entry.data[CONF_TARIFF]

    entities: list[SensorEntity] = [
        CurrentPriceSensor(coordinator, entry),
        CurrentOpustSensor(coordinator, entry),
    ]
    for zone in pricing.zone_ids(coordinator.data or {}, group):
        entities.append(ZonePriceSensor(coordinator, entry, zone))

    async_add_entities(entities)


class _BaseSensor(CoordinatorEntity[TariffCoordinator], SensorEntity):
    """Shared plumbing: device, units, hourly re-evaluation."""

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = UNIT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 4
    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator: TariffCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._group = entry.data[CONF_TARIFF]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer=entry.data[CONF_OPERATOR].upper(),
            model=self._group,
            entry_type=None,
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Zones change on the hour; re-evaluate at every full hour.
        self.async_on_remove(
            async_track_time_change(
                self.hass, self._handle_time, minute=0, second=5
            )
        )

    @callback
    def _handle_time(self, _now: datetime) -> None:
        self.async_write_ha_state()

    @property
    def _options(self) -> dict[str, Any]:
        return self._entry.options

    @property
    def _product(self) -> str | None:
        return self._options.get(CONF_PRODUCT)

    @property
    def _include_vat(self) -> bool:
        return self._options.get(CONF_INCLUDE_VAT, DEFAULT_INCLUDE_VAT)

    @property
    def _override(self) -> float | None:
        return self._options.get(CONF_ENERGY_OVERRIDE)

    def _price(self, zone: str, day) -> float | None:
        return pricing.consumption_price(
            self.coordinator.data or {},
            self._group,
            zone,
            day,
            self._product,
            self._include_vat,
            self._override,
        )


class CurrentPriceSensor(_BaseSensor):
    """Price for the zone that is active right now (for the Energy dashboard)."""

    _attr_translation_key = "current_price"
    _attr_icon = "mdi:cash"

    def __init__(self, coordinator: TariffCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_current_price"

    @property
    def native_value(self) -> float | None:
        now = dt_util.now()
        zone = pricing.active_zone(self._group, now)
        if zone is None:
            return None
        return self._price(zone, now.date())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        now = dt_util.now()
        day = now.date()
        data = self.coordinator.data or {}
        zones = pricing.zone_ids(data, self._group)
        return {
            "active_zone": pricing.active_zone(self._group, now),
            "energy_product": self._product,
            "vat_included": self._include_vat,
            "zone_prices": {z: self._price(z, day) for z in zones},
            "updated": data.get("updated"),
        }


class CurrentOpustSensor(_BaseSensor):
    """Net-metering credit (opust) for the currently active zone."""

    _attr_translation_key = "current_opust"
    _attr_icon = "mdi:solar-power"

    def __init__(self, coordinator: TariffCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_current_opust"

    @property
    def native_value(self) -> float | None:
        now = dt_util.now()
        zone = pricing.active_zone(self._group, now)
        if zone is None:
            return None
        return pricing.opust_price(
            self.coordinator.data or {},
            self._group,
            zone,
            now.date(),
            self._product,
            self._include_vat,
            self._override,
        )


class ZonePriceSensor(_BaseSensor):
    """Static price for one named zone (e.g. day / night)."""

    _attr_icon = "mdi:cash-clock"

    def __init__(
        self, coordinator: TariffCoordinator, entry: ConfigEntry, zone: str
    ) -> None:
        super().__init__(coordinator, entry)
        self._zone = zone
        self._attr_unique_id = f"{entry.entry_id}_price_{zone}"
        data = coordinator.data or {}
        label = (
            data.get("tariffs", {})
            .get(self._group, {})
            .get("zones", {})
            .get(zone, {})
            .get("label", zone)
        )
        self._attr_name = f"Cena {label}"

    @property
    def native_value(self) -> float | None:
        return self._price(self._zone, dt_util.now().date())
