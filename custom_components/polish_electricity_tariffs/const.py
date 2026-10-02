"""Constants for the Polish electricity tariffs integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "polish_electricity_tariffs"

DEFAULT_BASE_URL = "https://davo22.github.io/polish-electricity-tariffs/data/"

CONF_BASE_URL = "base_url"
CONF_OPERATOR = "operator"
CONF_TARIFF = "tariff"
CONF_PRODUCT = "energy_product"
CONF_PHASE = "phase"
CONF_ANNUAL_KWH = "annual_kwh"
CONF_ENERGY_OVERRIDE = "energy_override"
CONF_INCLUDE_VAT = "include_vat"

PHASE_1 = "1ph"
PHASE_3 = "3ph"

DEFAULT_INCLUDE_VAT = True
DEFAULT_PHASE = PHASE_1
DEFAULT_ANNUAL_KWH = 2000

# Tariff data changes ~yearly; refresh a couple of times a day is plenty.
UPDATE_INTERVAL = timedelta(hours=12)

ATTRIBUTION = "Dane: taryfy zatwierdzone przez URE (operatorzy dystrybucji i sprzedawcy)"
