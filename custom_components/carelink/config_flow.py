"""Config flow for carelink integration."""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .api import CarelinkClient
from .nightscout_uploader import NightscoutUploader
from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from the schema with values provided by the user.
    """
    client = CarelinkClient(
        data.setdefault("cl_refresh_token", None),
        data.setdefault("cl_token", None),
        data.setdefault("cl_client_id", None),
        data.setdefault("cl_client_secret", None),
        data.setdefault("cl_mag_identifier", None),
        data.setdefault("patientId", None)
    )

    try:
        if not await client.login():
            raise InvalidAuth
    finally:
        try:
            await client.close()
        except Exception:
            _LOGGER.warning("Failed to close Carelink client during validation")

    nightscout_url = data.setdefault("nightscout_url", None)
    nightscout_api = data.setdefault("nightscout_api", None)

    # Strip whitespace from URL if provided
    if nightscout_url:
        nightscout_url = nightscout_url.strip()
        data["nightscout_url"] = nightscout_url

    # Validate: if one is set, both must be set
    if bool(nightscout_url) != bool(nightscout_api):
        raise CannotConnect

    if nightscout_api and nightscout_url:
        # Validate URL format using urlparse
        parsed = urlparse(nightscout_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise CannotConnect

        uploader = NightscoutUploader(
            nightscout_url, nightscout_api
        )
        try:
            if not await uploader.reachServer():
                raise CannotConnect
        finally:
            try:
                await uploader.close()
            except Exception:
                _LOGGER.warning("Failed to close Nightscout uploader during validation")

    return {"title": "Carelink"}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for carelink."""

    VERSION = 1

    def _get_schema(self, defaults: dict[str, Any] | None = None, include_auth: bool = True) -> vol.Schema:
        """Generate the schema with optional default values."""
        if defaults is None:
            defaults = {}

        schema = {}

        # Only include auth fields if requested (e.g. initial setup)
        if include_auth:
            schema.update({
                vol.Optional("cl_token", description={"suggested_value": defaults.get("cl_token", "")}): str,
                vol.Optional("cl_refresh_token", description={"suggested_value": defaults.get("cl_refresh_token", "")}): str,
                vol.Optional("cl_client_id", description={"suggested_value": defaults.get("cl_client_id", "")}): str,
                vol.Optional("cl_client_secret", description={"suggested_value": defaults.get("cl_client_secret", "")}): str,
                vol.Optional("cl_mag_identifier", description={"suggested_value": defaults.get("cl_mag_identifier", "")}): str,
                vol.Optional("patientId", description={"suggested_value": defaults.get("patientId", "")}): str,
            })

        # Always include Nightscout and Scan Interval configuration
        schema.update({
            vol.Optional("nightscout_url", description={"suggested_value": defaults.get("nightscout_url", "")}): str,
            vol.Optional("nightscout_api", description={"suggested_value": defaults.get("nightscout_api", "")}): str,
            vol.Required(SCAN_INTERVAL, description={"suggested_value": defaults.get(SCAN_INTERVAL, 60)}): vol.All(vol.Coerce(int), vol.Range(min=30, max=300))
        })

        return vol.Schema(schema)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        # Show full form (Auth + Nightscout)
        return self.async_show_form(
            step_id="user",
            data_schema=self._get_schema(user_input, include_auth=True),
            errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle reconfiguration of the integration."""
        errors = {}
        
        # Get the current configuration entry
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])

        if user_input is not None:
            # Merge existing auth data (hidden from form) with new Nightscout input
            # This ensures validation passes using the credentials we already have
            full_config = {**entry.data, **user_input}

            try:
                await validate_input(self.hass, full_config)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    entry, data=full_config
                )

        # Prepare defaults: use user_input if a retry is happening, otherwise use stored entry data
        schema_defaults = user_input if user_input else dict(entry.data)

        # Show partial form (Nightscout Only + Scan Interval)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self._get_schema(schema_defaults, include_auth=False),
            errors=errors,
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
