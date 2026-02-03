"""Config flow for Network Monitor integration."""

from __future__ import annotations

import ipaddress
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback

from .const import (
    CONF_CHECK_INTERVAL,
    CONF_FULL_SCAN_INTERVAL,
    CONF_NETWORKS,
    CONF_OFFLINE_THRESHOLD,
    CONF_PING_TIMEOUT,
    DEFAULT_CHECK_INTERVAL,
    DEFAULT_FULL_SCAN_INTERVAL,
    DEFAULT_OFFLINE_THRESHOLD,
    DEFAULT_PING_TIMEOUT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def validate_networks(networks_str: str) -> list[str]:
    """Validate network ranges and return list of valid CIDRs."""
    networks = []
    for line in networks_str.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            # Validate CIDR notation
            network = ipaddress.ip_network(line, strict=False)
            networks.append(str(network))
        except ValueError as err:
            raise ValueError(f"Invalid network: {line}") from err
    if not networks:
        raise ValueError("At least one network range is required")
    return networks


class NetworkMonitorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Network Monitor."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._networks: list[str] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the network ranges step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                self._networks = validate_networks(user_input[CONF_NETWORKS])
                return await self.async_step_settings()
            except ValueError as err:
                _LOGGER.debug("Network validation error: %s", err)
                errors["base"] = "invalid_network"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_NETWORKS,
                        default="192.168.1.0/24",
                    ): str,
                }
            ),
            errors=errors,
            description_placeholders={"example": "192.168.1.0/24"},
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the scan settings step."""
        if user_input is not None:
            # Create the config entry
            return self.async_create_entry(
                title="Network Monitor",
                data={
                    CONF_NETWORKS: self._networks,
                },
                options={
                    CONF_FULL_SCAN_INTERVAL: user_input[CONF_FULL_SCAN_INTERVAL],
                    CONF_CHECK_INTERVAL: user_input[CONF_CHECK_INTERVAL],
                    CONF_PING_TIMEOUT: user_input[CONF_PING_TIMEOUT],
                    CONF_OFFLINE_THRESHOLD: user_input[CONF_OFFLINE_THRESHOLD],
                },
            )

        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_FULL_SCAN_INTERVAL,
                        default=DEFAULT_FULL_SCAN_INTERVAL,
                    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=1440)),
                    vol.Required(
                        CONF_CHECK_INTERVAL,
                        default=DEFAULT_CHECK_INTERVAL,
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
                    vol.Required(
                        CONF_PING_TIMEOUT,
                        default=DEFAULT_PING_TIMEOUT,
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
                    vol.Required(
                        CONF_OFFLINE_THRESHOLD,
                        default=DEFAULT_OFFLINE_THRESHOLD,
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow handler."""
        return NetworkMonitorOptionsFlow(config_entry)


class NetworkMonitorOptionsFlow(OptionsFlow):
    """Handle options flow for Network Monitor."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate networks
            try:
                networks = validate_networks(user_input[CONF_NETWORKS])
                # Update data with new networks
                self.hass.config_entries.async_update_entry(
                    self._config_entry,
                    data={CONF_NETWORKS: networks},
                )
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_FULL_SCAN_INTERVAL: user_input[CONF_FULL_SCAN_INTERVAL],
                        CONF_CHECK_INTERVAL: user_input[CONF_CHECK_INTERVAL],
                        CONF_PING_TIMEOUT: user_input[CONF_PING_TIMEOUT],
                        CONF_OFFLINE_THRESHOLD: user_input[CONF_OFFLINE_THRESHOLD],
                    },
                )
            except ValueError:
                errors["base"] = "invalid_network"

        # Get current values
        current_networks = "\n".join(self._config_entry.data.get(CONF_NETWORKS, []))
        options = self._config_entry.options

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_NETWORKS,
                        default=current_networks,
                    ): str,
                    vol.Required(
                        CONF_FULL_SCAN_INTERVAL,
                        default=options.get(
                            CONF_FULL_SCAN_INTERVAL, DEFAULT_FULL_SCAN_INTERVAL
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=1440)),
                    vol.Required(
                        CONF_CHECK_INTERVAL,
                        default=options.get(
                            CONF_CHECK_INTERVAL, DEFAULT_CHECK_INTERVAL
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
                    vol.Required(
                        CONF_PING_TIMEOUT,
                        default=options.get(CONF_PING_TIMEOUT, DEFAULT_PING_TIMEOUT),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
                    vol.Required(
                        CONF_OFFLINE_THRESHOLD,
                        default=options.get(
                            CONF_OFFLINE_THRESHOLD, DEFAULT_OFFLINE_THRESHOLD
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
                }
            ),
            errors=errors,
        )
