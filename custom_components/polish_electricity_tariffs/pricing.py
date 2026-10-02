"""Pure pricing logic for Polish electricity tariffs (no Home Assistant deps).

The data model is the schema-4 JSON served by the polish-electricity-tariffs
repo: distribution lives under ``tariffs`` (per group / zone / period),
energy under ``energy_products`` (per seller / offer), and the system-wide
components under ``system_components``.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any


def _pick_period(periods: list[dict] | None, day: date) -> dict | None:
    """Return the period whose [valid_from, valid_to] contains ``day``."""
    if not periods:
        return None
    iso = day.isoformat()
    for period in periods:
        start = period.get("valid_from", "0000-01-01")
        end = period.get("valid_to") or "9999-12-31"
        if start <= iso <= end:
            return period
    return None


def get_tariff_period(data: dict, group: str, day: date) -> dict | None:
    tariff = data.get("tariffs", {}).get(group)
    if not tariff:
        return None
    return _pick_period(tariff.get("periods"), day)


def get_system_components(data: dict, day: date) -> dict | None:
    return _pick_period(data.get("system_components"), day)


def _product(data: dict, product_id: str) -> dict | None:
    for product in data.get("energy_products", []):
        if product.get("id") == product_id:
            return product
    return None


def resolve_energy(
    data: dict,
    product_id: str | None,
    group: str,
    zone: str,
    day: date,
    override: float | None = None,
) -> float | None:
    """Resolve the net energy price (PLN/kWh) for a product/group/zone/date.

    ``override`` (a single flat net price) wins over everything when set.
    Returns ``None`` when no price can be determined (e.g. a dynamic product
    or a group the obligated seller does not price) — the caller then needs a
    user-provided price.
    """
    if override is not None:
        return override
    if not product_id:
        return None
    product = _product(data, product_id)
    if product is None:
        return None

    ptype = product.get("type")
    if ptype == "urzad_plus":
        base = resolve_energy(data, product.get("reference"), group, zone, day)
        delta = product.get("delta_net")
        if base is None or delta is None:
            return None
        return round(base + delta, 6)
    if ptype == "dynamic":
        # Hourly market price (RCE) + margin — no static number here.
        return None

    period = _pick_period(product.get("periods"), day)
    if period is None:
        return None
    if "flat_price_net" in period:
        return period["flat_price_net"]
    group_prices = period.get("prices_net", {}).get(group)
    if not group_prices:
        return None
    return group_prices.get(zone)


# --- Polish public holidays (needed for weekend/holiday off-peak zones) ---


def _easter(year: int) -> date:
    """Gregorian (Anonymous) computus for Easter Sunday."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    month, day = divmod(h + m - 7 * n + 114, 31)
    return date(year, month, day + 1)


def _holidays(year: int) -> set[date]:
    easter = _easter(year)
    from datetime import timedelta

    movable = {
        easter,  # Wielkanoc
        easter + timedelta(days=1),  # Poniedziałek Wielkanocny
        easter + timedelta(days=49),  # Zielone Świątki
        easter + timedelta(days=60),  # Boże Ciało
    }
    fixed = {
        date(year, 1, 1),  # Nowy Rok
        date(year, 1, 6),  # Trzech Króli
        date(year, 5, 1),  # Święto Pracy
        date(year, 5, 3),  # Święto Konstytucji
        date(year, 8, 15),  # Wniebowzięcie NMP
        date(year, 11, 1),  # Wszystkich Świętych
        date(year, 11, 11),  # Niepodległości
        date(year, 12, 25),
        date(year, 12, 26),
    }
    return movable | fixed


def is_free_day(day: date) -> bool:
    """True for Saturdays, Sundays and Polish public holidays."""
    return day.weekday() >= 5 or day in _holidays(day.year)


def _is_summer(day: date) -> bool:
    """G13/G13s season: summer = 1 Apr – 30 Sep."""
    return 4 <= day.month <= 9


def active_zone(group: str, moment: datetime) -> str | None:
    """Which zone is active at ``moment`` for the given tariff group.

    Returns ``None`` when the schedule cannot be determined statically
    (G13s requires season+day-type handling that we fold into G13-style
    zones only partially; G14dynamic needs the PSE Energetyczny Kompas feed).
    """
    hour = moment.hour
    day = moment.date()
    free = is_free_day(day)

    if group == "G11":
        return "all"

    if group == "G12":
        # day 06-13, 15-22 ; night 22-06, 13-15
        return "day" if (6 <= hour < 13 or 15 <= hour < 22) else "night"

    if group == "G12as":
        # day 06-22 ; night 22-06
        return "day" if 6 <= hour < 22 else "night"

    if group == "G12w":
        if free:
            return "offpeak"
        return "peak" if (6 <= hour < 13 or 15 <= hour < 22) else "offpeak"

    if group == "G13":
        if free:
            return "off_peak"
        if 7 <= hour < 13:
            return "morning_peak"
        if _is_summer(day):
            afternoon = 19 <= hour < 22
        else:
            afternoon = 16 <= hour < 21
        return "afternoon_peak" if afternoon else "off_peak"

    # G13s (nested season/day-type distribution) and G14dynamic (PSE Kompas)
    # are not schedulable from static JSON alone.
    return None


def zone_ids(data: dict, group: str) -> list[str]:
    tariff = data.get("tariffs", {}).get(group, {})
    return list(tariff.get("zones", {}).keys())


def _distribution_for_zone(period: dict, zone: str) -> float | None:
    dist = period.get("distribution_variable_net", {})
    value = dist.get(zone)
    if isinstance(value, (int, float)):
        return float(value)
    # G12as exposes the night charge as within/above baseline; use the
    # normal (within-baseline) rate for a "night" lookup.
    if zone == "night":
        return dist.get("night_within_baseline")
    return None


def consumption_price(
    data: dict,
    group: str,
    zone: str,
    day: date,
    product_id: str | None,
    include_vat: bool = True,
    energy_override: float | None = None,
) -> float | None:
    """Gross (or net) per-kWh consumption price for a group/zone/date."""
    tariff_period = get_tariff_period(data, group, day)
    system = get_system_components(data, day)
    if tariff_period is None or system is None:
        return None

    energy = resolve_energy(data, product_id, group, zone, day, energy_override)
    distribution = _distribution_for_zone(tariff_period, zone)
    if energy is None or distribution is None:
        return None

    net = (
        energy
        + distribution
        + system.get("quality_net", 0.0)
        + system.get("oze_net", 0.0)
        + system.get("cogeneration_net", 0.0)
    )
    vat = data.get("vat", 0.0) if include_vat else 0.0
    return round(net * (1 + vat), 4)


def opust_price(
    data: dict,
    group: str,
    zone: str,
    day: date,
    product_id: str | None,
    include_vat: bool = True,
    energy_override: float | None = None,
) -> float | None:
    """Net-metering credit (opust) per kWh for a group/zone/date."""
    tariff = data.get("tariffs", {}).get(group, {})
    components = tariff.get("opust_components")
    if not components:  # None or empty -> net-metering does not apply
        return None

    tariff_period = get_tariff_period(data, group, day)
    system = get_system_components(data, day)
    if tariff_period is None or system is None:
        return None

    factor = data.get("net_metering_factor", 1.0)
    total = 0.0
    for comp in components:
        if comp == "energy":
            value = resolve_energy(
                data, product_id, group, zone, day, energy_override
            )
        elif comp == "distribution_variable":
            value = _distribution_for_zone(tariff_period, zone)
        else:
            value = system.get(f"{comp}_net")
        if value is None:
            return None
        total += value

    vat = data.get("vat", 0.0) if include_vat else 0.0
    return round(factor * total * (1 + vat), 4)
