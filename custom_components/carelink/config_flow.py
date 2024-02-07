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
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("country"): str,
        vol.Required("token"): str,
        vol.Optional("patientId"): str,
        vol.Optional("nightscout_url"): str,
        vol.Optional("nightscout_api"): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """

    patient_id = None
    if "patientId" in data:
        patient_id = data["patientId"]

    client = CarelinkClient(
        data["country"], data["token"], patient_id
    )

    if not await client.login():
        raise InvalidAuth

    nightscout_url = None
    nightscout_api = None
    if "nightscout_url" in data:
        nightscout_url = data["nightscout_url"]
    if "nightscout_api" in data:
        nightscout_api = data["nightscout_api"]

    if nightscout_api and nightscout_url:
        uploader = NightscoutUploader(
            data["nightscout_url"], data["nightscout_api"]
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
