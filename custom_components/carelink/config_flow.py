"""Config flow for carelink integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .api import CarelinkClient
from .nightscout_uploader import NightscoutUploader
from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Optional("cl_token"): str,
        vol.Optional("cl_refresh_token"): str,
        vol.Optional("cl_client_id"): str,
        vol.Optional("cl_client_secret"): str,
        vol.Optional("cl_mag_identifier"): str,
        vol.Optional("patientId"): str,
        vol.Optional("nightscout_url"): str,
        vol.Optional("nightscout_api"): str,
        vol.Required(SCAN_INTERVAL, default=60): vol.All(vol.Coerce(int), vol.Range(min=30, max=300)),
    }
)

async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """

    client = CarelinkClient(
        data.setdefault("cl_token", None),
        data.setdefault("cl_refresh_token", None),
        data.setdefault("cl_client_id", None),
        data.setdefault("cl_client_secret", None),
        data.setdefault("cl_mag_identifier", None),
        data.setdefault("patientId", None)
    )

    if not await client.login():
        raise InvalidAuth

    nightscout_url = data.setdefault("nightscout_url", None)
    nightscout_api = data.setdefault("nightscout_api", None)
    if nightscout_api and nightscout_url:
        uploader = NightscoutUploader(
            nightscout_url, nightscout_api
        )
        if not await uploader.reachServer():
            raise ConnectionError

    return {"title": "Carelink"}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for carelink."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        errors = {}

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

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
