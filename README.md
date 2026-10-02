# Polish electricity tariffs — Home Assistant integration

Pulls Polish electricity prices into Home Assistant so you don't have to type
your per-kWh rates by hand. You pick an **operator**, a **tariff group** and an
**energy offer**; the integration fetches the regulated distribution rates and
the energy price from a small static dataset and exposes **current-price
sensors** you can drop straight into the Energy dashboard.

Data source (static JSON over GitHub Pages, no server, no scraping):
<https://github.com/davo22/polish-electricity-tariffs> — tariffs approved by
**URE** (the regulator), covering TAURON household groups G11, G12, G12w, G12as,
G13, G13s, G14dynamic.

## What you get

- **Aktualna cena** (`sensor` current price) — the gross PLN/kWh for the zone
  that is active *right now*. Zones switch on the hour (day/night, weekend,
  season, holidays are handled for G11/G12/G12as/G12w/G13). Use this as the
  "entity with current price" in the Energy dashboard.
- **Aktualny opust** — the net-metering credit (opust) per kWh for prosumers.
- **One price sensor per zone** (e.g. day / night) for reference.

Attributes expose the active zone, every zone's price, the chosen energy product
and whether VAT is included.

## Install (HACS)

1. HACS → Integrations → ⋮ → *Custom repositories* → add
   `https://github.com/davo22/ha-polish-electricity-tariffs` (type: Integration).
2. Install **Polish electricity tariffs**, then restart Home Assistant.
3. Settings → Devices & Services → *Add integration* → **Polish electricity
   tariffs**.

Then pick: data source (keep the default), operator, tariff group, and the
offer + settings:

- **Oferta energii** — `Sprzedawca z urzędu` (regulated default) or a listed
  market offer.
- **Przyłącze** — 1- or 3-phase (affects the fixed network fee only).
- **Roczne zużycie** — used to pick the right capacity-fee band (fixed fee).
- **Ceny brutto** — on = gross (what you pay), off = net.
- **Nadpisanie ceny energii** — optional: your own contract's net energy price
  (PLN/kWh). Leave empty to use the offer. Needed for groups with no
  obligated-seller price (G12as/G13s) or any custom offer.

Change any of these later via the integration's **Configure** (options).

## Notes & limits

- Energy prices for market offers are volatile; the dataset curates the
  regulated default plus a few examples, so for many offers you'll set your own
  price via the override.
- `G14dynamic` uses hourly market pricing (RCE) via the PSE Energetyczny Kompas
  — its current-price sensor is not computed statically; distribution-only.
- `G13s` current-zone depends on season + day-type nesting and is not scheduled
  automatically yet; its distribution data is present for reference.

## License

[MIT](LICENSE) © Dawid Rashid. Not affiliated with TAURON, URE, or any operator.
