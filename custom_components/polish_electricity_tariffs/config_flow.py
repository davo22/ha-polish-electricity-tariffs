"""Config and options flow."""

from __future__ import annotations

from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .const import (
    CONF_ANNUAL_KWH,
    CONF_BASE_URL,
    CONF_ENERGY_OVERRIDE,
    CONF_INCLUDE_VAT,
    CONF_OPERATOR,
    CONF_PHASE,
    CONF_PRODUCT,
    CONF_TARIFF,
    DEFAULT_ANNUAL_KWH,
    DEFAULT_BASE_URL,
    DEFAULT_INCLUDE_VAT,
    DEFAULT_PHASE,
    DOMAIN,
    PHASE_1,
    PHASE_3,
)
from .coordinator import async_fetch_index, async_fetch_operator


def _parse_override(raw: str | None) -> float | None:
    if raw is None or str(raw).strip() == "":
        return None
    return float(str(raw).replace(",", "."))


def _options_schema(operator_data: dict, options: dict | None = None) -> vol.Schema:
    options = options or {}
    products = [
        SelectOptionDict(value=p["id"], label=p.get("name", p["id"]))
        for p in operator_data.get("energy_products", [])
    ]
    default_product = operator_data.get("default_energy_product") or (
        products[0]["value"] if products else ""
    )
    override = options.get(CONF_ENERGY_OVERRIDE)
    return vol.Schema(
        {
            vol.Required(
                CONF_PRODUCT, default=options.get(CONF_PRODUCT, default_product)
            ): SelectSelector(
                SelectSelectorConfig(options=products, mode=SelectSelectorMode.DROPDOWN)
            ),
            vol.Required(
                CONF_PHASE, default=options.get(CONF_PHASE, DEFAULT_PHASE)
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(value=PHASE_1, label="1-fazowy"),
                        SelectOptionDict(value=PHASE_3, label="3-fazowy"),
                    ],
                    mode=SelectSelectorMode.LIST,
                )
            ),
            vol.Required(
                CONF_ANNUAL_KWH,
                default=options.get(CONF_ANNUAL_KWH, DEFAULT_ANNUAL_KWH),
            ): vol.All(vol.Coerce(int), vol.Range(min=0)),
            vol.Required(
                CONF_INCLUDE_VAT,
                default=options.get(CONF_INCLUDE_VAT, DEFAULT_INCLUDE_VAT),
            ): BooleanSelector(),
            vol.Optional(
                CONF_ENERGY_OVERRIDE,
                description={"suggested_value": "" if override is None else str(override)},
            ): TextSelector(),
        }
    )


class PetConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._base_url = DEFAULT_BASE_URL
        self._index: dict[str, Any] = {}
        self._operator: dict[str, Any] = {}
        self._operator_entry: dict[str, Any] = {}
        self._tariff: str = ""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._base_url = user_input.get(CONF_BASE_URL, DEFAULT_BASE_URL)
            try:
                self._index = await async_fetch_index(self.hass, self._base_url)
            except (aiohttp.ClientError, ValueError):
                errors["base"] = "cannot_connect"
            else:
                return await self.async_step_operator()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_BASE_URL, default=DEFAULT_BASE_URL): TextSelector()}
            ),
            errors=errors,
        )

    async def async_step_operator(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        operators = self._index.get("operators", [])
        if user_input is not None:
            self._operator_entry = next(
                o for o in operators if o["id"] == user_input[CONF_OPERATOR]
            )
            try:
                self._operator = await async_fetch_operator(
                    self.hass, self._base_url, self._operator_entry["file"]
                )
            except (aiohttp.ClientError, ValueError):
                errors["base"] = "cannot_connect"
            else:
                return await self.async_step_tariff()

        return self.async_show_form(
            step_id="operator",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_OPERATOR): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(value=o["id"], label=o["name"])
                                for o in operators
                            ],
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_tariff(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._tariff = user_input[CONF_TARIFF]
            return await self.async_step_options()

        groups = list(self._operator.get("tariffs", {}).keys())
        return self.async_show_form(
            step_id="tariff",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TARIFF): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(
                                    value=g,
                                    label=self._operator["tariffs"][g].get("name", g),
                                )
                                for g in groups
                            ],
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_options(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                override = _parse_override(user_input.get(CONF_ENERGY_OVERRIDE))
            except ValueError:
                errors["base"] = "invalid_override"
            else:
                options = {
                    CONF_PRODUCT: user_input[CONF_PRODUCT],
                    CONF_PHASE: user_input[CONF_PHASE],
                    CONF_ANNUAL_KWH: user_input[CONF_ANNUAL_KWH],
                    CONF_INCLUDE_VAT: user_input[CONF_INCLUDE_VAT],
                }
                if override is not None:
                    options[CONF_ENERGY_OVERRIDE] = override

                await self.async_set_unique_id(
                    f"{self._operator_entry['id']}_{self._tariff}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"{self._operator_entry['name']} {self._tariff}",
                    data={
                        CONF_BASE_URL: self._base_url,
                        CONF_OPERATOR: self._operator_entry["id"],
                        "file": self._operator_entry["file"],
                        CONF_TARIFF: self._tariff,
                    },
                    options=options,
                )

        return self.async_show_form(
            step_id="options",
            data_schema=_options_schema(self._operator),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return PetOptionsFlow()


class PetOptionsFlow(OptionsFlow):
    """Allow editing product / phase / annual kWh / VAT / override."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        coordinator = self.hass.data[DOMAIN][self.config_entry.entry_id]
        operator_data = coordinator.data or {}

        if user_input is not None:
            try:
                override = _parse_override(user_input.get(CONF_ENERGY_OVERRIDE))
            except ValueError:
                errors["base"] = "invalid_override"
            else:
                options = {
                    CONF_PRODUCT: user_input[CONF_PRODUCT],
                    CONF_PHASE: user_input[CONF_PHASE],
                    CONF_ANNUAL_KWH: user_input[CONF_ANNUAL_KWH],
                    CONF_INCLUDE_VAT: user_input[CONF_INCLUDE_VAT],
                }
                if override is not None:
                    options[CONF_ENERGY_OVERRIDE] = override
                return self.async_create_entry(title="", data=options)

        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(operator_data, dict(self.config_entry.options)),
            errors=errors,
        )
