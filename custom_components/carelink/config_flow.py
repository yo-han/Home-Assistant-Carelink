"""Config flow for carelink integration."""
from __future__ import annotations

import ipaddress
import logging
import socket
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .api import CarelinkClient
from .tandem_api import TandemSourceClient, TandemAuthError
from .nightscout_uploader import NightscoutUploader
from .const import (
    DOMAIN,
    SCAN_INTERVAL,
    PLATFORM_TYPE,
    PLATFORM_CARELINK,
    PLATFORM_TANDEM,
)

_LOGGER = logging.getLogger(__name__)


async def validate_carelink_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate Carelink (Medtronic) user input."""
    client = CarelinkClient(
        data.setdefault("cl_refresh_token", None),
        data.setdefault("cl_token", None),
        data.setdefault("cl_client_id", None),
        data.setdefault("cl_client_secret", None),
        data.setdefault("cl_mag_identifier", None),
        data.setdefault("patientId", None),
        config_path=hass.config.path()
    )

    try:
        if not await client.login():
            raise InvalidAuth
    finally:
        try:
            await client.close()
        except Exception:
            _LOGGER.warning("Failed to close Carelink client during validation")

    await _validate_nightscout(hass, data)

    return {"title": "Carelink"}


async def validate_tandem_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate Tandem Source user input."""
    email = data.get("tandem_email", "").strip()
    password = data.get("tandem_password", "")
    region = data.get("tandem_region", "EU")

    if not email or not password:
        raise InvalidAuth

    client = TandemSourceClient(email, password, region)
    try:
        if not await client.login():
            raise InvalidAuth
    except TandemAuthError as e:
        _LOGGER.warning("Tandem login failed: %s", e)
        raise InvalidAuth from e
    finally:
        try:
            await client.close()
        except Exception:
            _LOGGER.warning("Failed to close Tandem client during validation")

    await _validate_nightscout(hass, data)

    return {"title": f"Tandem t:slim ({region})"}


async def _validate_nightscout(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Validate Nightscout configuration if provided."""
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

        # SSRF protection: reject URLs targeting private/reserved networks
        hostname = parsed.hostname or ""
        try:
            # Resolve hostname to detect private IPs behind DNS names
            addr_info = socket.getaddrinfo(hostname, None)
            for _family, _type, _proto, _canonname, sockaddr in addr_info:
                ip = ipaddress.ip_address(sockaddr[0])
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                    _LOGGER.warning(
                        "Nightscout URL resolves to non-routable address, rejected"
                    )
                    raise CannotConnect
        except socket.gaierror:
            # DNS resolution failed — let it fail later at connection time
            pass

        uploader = NightscoutUploader(nightscout_url, nightscout_api)
        try:
            if not await uploader.reachServer():
                raise CannotConnect
        finally:
            try:
                await uploader.close()
            except Exception:
                _LOGGER.warning("Failed to close Nightscout uploader during validation")


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for carelink."""

    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self._platform_type: str | None = None

    # ── Step 1: Choose platform ──────────────────────────────────────────

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle platform selection step."""
        if user_input is not None:
            self._platform_type = user_input.get(PLATFORM_TYPE, PLATFORM_CARELINK)
            if self._platform_type == PLATFORM_TANDEM:
                return await self.async_step_tandem()
            return await self.async_step_carelink()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(
                    PLATFORM_TYPE, default=PLATFORM_CARELINK
                ): vol.In({
                    PLATFORM_CARELINK: "Medtronic CareLink",
                    PLATFORM_TANDEM: "Tandem t:slim (Source)",
                }),
            }),
        )

    # ── Step 2a: Carelink configuration ──────────────────────────────────

    def _get_carelink_schema(self, defaults: dict[str, Any] | None = None, include_auth: bool = True) -> vol.Schema:
        """Generate the Carelink schema with optional default values."""
        if defaults is None:
            defaults = {}

        schema = {}

        if include_auth:
            schema.update({
                vol.Optional("cl_token", description={"suggested_value": defaults.get("cl_token", "")}): str,
                vol.Optional("cl_refresh_token", description={"suggested_value": defaults.get("cl_refresh_token", "")}): str,
                vol.Optional("cl_client_id", description={"suggested_value": defaults.get("cl_client_id", "")}): str,
                vol.Optional("cl_client_secret", description={"suggested_value": defaults.get("cl_client_secret", "")}): str,
                vol.Optional("cl_mag_identifier", description={"suggested_value": defaults.get("cl_mag_identifier", "")}): str,
                vol.Optional("patientId", description={"suggested_value": defaults.get("patientId", "")}): str,
            })

        schema.update({
            vol.Optional("nightscout_url", description={"suggested_value": defaults.get("nightscout_url", "")}): str,
            vol.Optional("nightscout_api", description={"suggested_value": defaults.get("nightscout_api", "")}): str,
            vol.Required(SCAN_INTERVAL, description={"suggested_value": defaults.get(SCAN_INTERVAL, 60)}): vol.All(vol.Coerce(int), vol.Range(min=30, max=300))
        })

        return vol.Schema(schema)

    async def async_step_carelink(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle Carelink configuration step."""
        errors = {}

        if user_input is not None:
            user_input[PLATFORM_TYPE] = PLATFORM_CARELINK
            try:
                info = await validate_carelink_input(self.hass, user_input)
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
            step_id="carelink",
            data_schema=self._get_carelink_schema(user_input, include_auth=True),
            errors=errors
        )

    # ── Step 2b: Tandem configuration ────────────────────────────────────

    def _get_tandem_schema(self, defaults: dict[str, Any] | None = None, include_auth: bool = True) -> vol.Schema:
        """Generate the Tandem schema with optional default values."""
        if defaults is None:
            defaults = {}

        schema = {}

        if include_auth:
            schema.update({
                vol.Required("tandem_email", description={"suggested_value": defaults.get("tandem_email", "")}): str,
                vol.Required("tandem_password", description={"suggested_value": defaults.get("tandem_password", "")}): str,
                vol.Required("tandem_region", default=defaults.get("tandem_region", "EU")): vol.In({
                    "EU": "Europe",
                    "US": "United States",
                }),
            })

        schema.update({
            vol.Optional("nightscout_url", description={"suggested_value": defaults.get("nightscout_url", "")}): str,
            vol.Optional("nightscout_api", description={"suggested_value": defaults.get("nightscout_api", "")}): str,
            vol.Required(SCAN_INTERVAL, description={"suggested_value": defaults.get(SCAN_INTERVAL, 300)}): vol.All(vol.Coerce(int), vol.Range(min=60, max=900))
        })

        return vol.Schema(schema)

    async def async_step_tandem(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle Tandem Source configuration step."""
        errors = {}

        if user_input is not None:
            user_input[PLATFORM_TYPE] = PLATFORM_TANDEM
            try:
                info = await validate_tandem_input(self.hass, user_input)
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
            step_id="tandem",
            data_schema=self._get_tandem_schema(user_input, include_auth=True),
            errors=errors
        )

    # ── Reconfiguration ──────────────────────────────────────────────────

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle reconfiguration of the integration."""
        errors = {}

        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        platform = entry.data.get(PLATFORM_TYPE, PLATFORM_CARELINK)

        if user_input is not None:
            full_config = {**entry.data, **user_input}

            try:
                if platform == PLATFORM_TANDEM:
                    await validate_tandem_input(self.hass, full_config)
                else:
                    await validate_carelink_input(self.hass, full_config)
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

        schema_defaults = user_input if user_input else dict(entry.data)

        if platform == PLATFORM_TANDEM:
            schema = self._get_tandem_schema(schema_defaults, include_auth=False)
        else:
            schema = self._get_carelink_schema(schema_defaults, include_auth=False)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema,
            errors=errors,
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
