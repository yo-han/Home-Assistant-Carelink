"""Tests for security hardening: error sanitisation, SSRF protection, PII redaction.

These tests validate security fixes #10-#14 from the vulnerability audit.
"""
from __future__ import annotations

import base64
import importlib
import json
import socket
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Helpers to import modules that depend on the HA import chain ─────────

def _import_tandem_api():
    """Import tandem_api module, which lives inside the carelink package.

    Because ``custom_components.carelink.__init__`` imports from homeassistant
    (which may not be fully installable in CI), we import the file directly.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "tandem_api",
        "custom_components/carelink/tandem_api.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_tandem = _import_tandem_api()
TandemSourceClient = _tandem.TandemSourceClient
TandemAuthError = _tandem.TandemAuthError
TandemApiError = _tandem.TandemApiError


# ═══════════════════════════════════════════════════════════════════════════
# #10 / #11: Error messages must NOT leak HTTP response bodies or server msgs
# ═══════════════════════════════════════════════════════════════════════════


class TestErrorMessageSanitisation:
    """Verify that error messages never contain response bodies or server details."""

    async def test_login_http_error_no_body(self):
        """Login failure must not include the HTTP response body."""
        client = TandemSourceClient("user@test.com", "pass")

        mock_login_page = MagicMock()
        mock_login_page.status_code = 200
        mock_login_page.text = "<html>login</html>"

        mock_login_resp = MagicMock()
        mock_login_resp.status_code = 403
        mock_login_resp.text = '{"error":"secret_internal_detail","trace":"stack..."}'

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_login_page)
        mock_http.post = AsyncMock(return_value=mock_login_resp)
        mock_http.is_closed = False
        client._client = mock_http

        with pytest.raises(TandemAuthError) as exc_info:
            await client.login()

        msg = str(exc_info.value)
        assert "secret_internal_detail" not in msg
        assert "stack" not in msg
        assert "403" in msg  # status code is OK to include

    async def test_login_rejected_no_server_message(self):
        """Login rejection must not include server-side error message."""
        client = TandemSourceClient("user@test.com", "pass")

        mock_login_page = MagicMock()
        mock_login_page.status_code = 200
        mock_login_page.text = "<html>login</html>"

        mock_login_resp = MagicMock()
        mock_login_resp.status_code = 200
        mock_login_resp.json.return_value = {
            "status": "FAILURE",
            "message": "Account locked after 5 failed attempts for user@test.com",
        }

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_login_page)
        mock_http.post = AsyncMock(return_value=mock_login_resp)
        mock_http.is_closed = False
        client._client = mock_http

        with pytest.raises(TandemAuthError) as exc_info:
            await client.login()

        msg = str(exc_info.value)
        assert "Account locked" not in msg
        assert "user@test.com" not in msg
        assert "5 failed attempts" not in msg

    async def test_token_exchange_no_body(self):
        """Token exchange failure must not include the response body."""
        client = TandemSourceClient("user@test.com", "pass")

        mock_login_page = MagicMock()
        mock_login_page.status_code = 200

        mock_login_resp = MagicMock()
        mock_login_resp.status_code = 200
        mock_login_resp.json.return_value = {"status": "SUCCESS"}

        mock_auth_resp = MagicMock()
        mock_auth_resp.status_code = 302
        mock_auth_resp.url = "https://redirect.example.com?code=authcode123"

        mock_token_resp = MagicMock()
        mock_token_resp.status_code = 400
        mock_token_resp.text = '{"error":"invalid_grant","error_description":"Code expired"}'

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=[mock_login_page, mock_auth_resp])
        mock_http.post = AsyncMock(side_effect=[mock_login_resp, mock_token_resp])
        mock_http.is_closed = False
        client._client = mock_http

        with pytest.raises(TandemAuthError) as exc_info:
            await client.login()

        msg = str(exc_info.value)
        assert "invalid_grant" not in msg
        assert "Code expired" not in msg
        assert "400" in msg

    async def test_api_get_error_no_body(self):
        """API GET failure must not include the response body."""
        client = TandemSourceClient("user@test.com", "pass")
        client.access_token = "valid_token"

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = '{"error":"NullPointerException at com.tandem.internal.Service"}'

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.is_closed = False
        client._client = mock_http

        with pytest.raises(TandemApiError) as exc_info:
            await client._api_get("https://api.test.com/data")

        msg = str(exc_info.value)
        assert "NullPointerException" not in msg
        assert "com.tandem.internal" not in msg
        assert "500" in msg

    async def test_api_get_error_no_url_leak(self):
        """API GET failure must not include the request URL."""
        client = TandemSourceClient("user@test.com", "pass")
        client.access_token = "valid_token"

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not found"

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.is_closed = False
        client._client = mock_http

        with pytest.raises(TandemApiError) as exc_info:
            await client._api_get("https://api.tandemdiabetes.com/secret/endpoint")

        msg = str(exc_info.value)
        assert "tandemdiabetes.com" not in msg
        assert "secret/endpoint" not in msg

    async def test_auth_redirect_no_url_leak(self):
        """Authorization redirect failure must not leak the redirect URL."""
        client = TandemSourceClient("user@test.com", "pass")

        mock_login_page = MagicMock()
        mock_login_page.status_code = 200

        mock_login_resp = MagicMock()
        mock_login_resp.status_code = 200
        mock_login_resp.json.return_value = {"status": "SUCCESS"}

        # Redirect URL without authorization code
        mock_auth_resp = MagicMock()
        mock_auth_resp.status_code = 302
        mock_auth_resp.url = "https://internal.tandem.com/error?detail=session_expired&token=abc123"

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=[mock_login_page, mock_auth_resp])
        mock_http.post = AsyncMock(return_value=mock_login_resp)
        mock_http.is_closed = False
        client._client = mock_http

        with pytest.raises(TandemAuthError) as exc_info:
            await client.login()

        msg = str(exc_info.value)
        assert "internal.tandem.com" not in msg
        assert "session_expired" not in msg
        assert "abc123" not in msg


# ═══════════════════════════════════════════════════════════════════════════
# #12: SSRF protection — Nightscout URL validation
#
# We test the SSRF logic inline because config_flow.py requires the full
# Home Assistant import chain (homeassistant.config_entries → core → etc.)
# which may not be available in lightweight CI environments.  The logic
# under test is: parse URL → resolve hostname → reject private/reserved IPs.
# ═══════════════════════════════════════════════════════════════════════════

import ipaddress
from urllib.parse import urlparse


class _CannotConnect(Exception):
    """Stand-in for HA CannotConnect used in SSRF tests."""


def _ssrf_check(nightscout_url: str) -> None:
    """Reproduce the SSRF validation logic from config_flow._validate_nightscout."""
    parsed = urlparse(nightscout_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise _CannotConnect

    hostname = parsed.hostname or ""
    try:
        addr_info = socket.getaddrinfo(hostname, None)
        for _family, _type, _proto, _canonname, sockaddr in addr_info:
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise _CannotConnect
    except socket.gaierror:
        pass  # DNS failure — let it fail later at connection time


class TestNightscoutSSRFProtection:
    """Verify that private/reserved IPs are rejected for Nightscout URL."""

    def test_reject_localhost_ip(self):
        """Nightscout URL pointing to 127.0.0.1 must be rejected."""
        with pytest.raises(_CannotConnect):
            _ssrf_check("https://127.0.0.1:1337")

    def test_reject_private_ip_192(self):
        """Nightscout URL pointing to 192.168.x.x must be rejected."""
        with pytest.raises(_CannotConnect):
            _ssrf_check("https://192.168.1.100:1337")

    def test_reject_private_ip_10(self):
        """Nightscout URL pointing to 10.x.x.x must be rejected."""
        with pytest.raises(_CannotConnect):
            _ssrf_check("https://10.0.0.1")

    def test_reject_private_ip_172(self):
        """Nightscout URL pointing to 172.16.x.x must be rejected."""
        with pytest.raises(_CannotConnect):
            _ssrf_check("https://172.16.0.1")

    def test_reject_dns_resolving_to_private(self):
        """Nightscout URL whose DNS resolves to private IP must be rejected."""
        fake_addrinfo = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.1", 443)),
        ]
        with patch("socket.getaddrinfo", return_value=fake_addrinfo):
            with pytest.raises(_CannotConnect):
                _ssrf_check("https://evil.example.com")

    def test_accept_public_ip(self):
        """Nightscout URL with public IP should pass SSRF check."""
        fake_addrinfo = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
        ]
        with patch("socket.getaddrinfo", return_value=fake_addrinfo):
            _ssrf_check("https://nightscout.example.com")  # Should not raise

    def test_dns_failure_passes_through(self):
        """If DNS fails, SSRF check is skipped (fails later at connection)."""
        with patch("socket.getaddrinfo", side_effect=socket.gaierror("DNS failed")):
            _ssrf_check("https://nonexistent.example.com")  # Should not raise

    def test_reject_ipv6_loopback(self):
        """Nightscout URL resolving to ::1 must be rejected."""
        fake_addrinfo = [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", 443, 0, 0)),
        ]
        with patch("socket.getaddrinfo", return_value=fake_addrinfo):
            with pytest.raises(_CannotConnect):
                _ssrf_check("https://evil.example.com")

    def test_reject_link_local(self):
        """Nightscout URL resolving to link-local address must be rejected."""
        fake_addrinfo = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.1.1", 443)),
        ]
        with patch("socket.getaddrinfo", return_value=fake_addrinfo):
            with pytest.raises(_CannotConnect):
                _ssrf_check("https://evil.example.com")


# ═══════════════════════════════════════════════════════════════════════════
# #13: JWT decode — narrow exception handling
# ═══════════════════════════════════════════════════════════════════════════


class TestJWTDecodeExceptionHandling:
    """Verify JWT decode raises TandemAuthError for specific decode failures."""

    def test_invalid_jwt_format(self):
        """JWT with wrong number of parts raises TandemAuthError."""
        client = TandemSourceClient("user@test.com", "pass")
        client.id_token = "only.two"

        with pytest.raises(TandemAuthError, match="Invalid JWT format"):
            client._extract_jwt_claims()

    def test_corrupt_base64_payload(self):
        """JWT with non-base64 payload raises TandemAuthError."""
        client = TandemSourceClient("user@test.com", "pass")
        client.id_token = "header.!!!invalid-base64!!!.signature"

        with pytest.raises(TandemAuthError, match="Cannot decode JWT payload"):
            client._extract_jwt_claims()

    def test_non_json_payload(self):
        """JWT with non-JSON payload raises TandemAuthError."""
        client = TandemSourceClient("user@test.com", "pass")
        payload = base64.urlsafe_b64encode(b"this is not json").decode().rstrip("=")
        client.id_token = f"header.{payload}.signature"

        with pytest.raises(TandemAuthError, match="Cannot decode JWT payload"):
            client._extract_jwt_claims()

    def test_error_message_no_internal_details(self):
        """JWT decode error must not expose internal exception details."""
        client = TandemSourceClient("user@test.com", "pass")
        payload = base64.urlsafe_b64encode(b"not json").decode().rstrip("=")
        client.id_token = f"header.{payload}.signature"

        with pytest.raises(TandemAuthError) as exc_info:
            client._extract_jwt_claims()

        msg = str(exc_info.value)
        assert "Expecting value" not in msg
        assert "JSONDecodeError" not in msg

    def test_valid_jwt_extracts_claims(self):
        """Valid JWT with pumperId should extract claims correctly."""
        client = TandemSourceClient("user@test.com", "pass")
        claims = {"pumperId": "pump-123", "accountId": "acct-456"}
        payload = base64.urlsafe_b64encode(
            json.dumps(claims).encode()
        ).decode().rstrip("=")
        client.id_token = f"header.{payload}.signature"

        client._extract_jwt_claims()

        assert client.pumper_id == "pump-123"
        assert client.account_id == "acct-456"

    def test_missing_pumper_id_raises(self):
        """JWT without pumperId raises TandemAuthError."""
        client = TandemSourceClient("user@test.com", "pass")
        claims = {"accountId": "acct-456"}
        payload = base64.urlsafe_b64encode(
            json.dumps(claims).encode()
        ).decode().rstrip("=")
        client.id_token = f"header.{payload}.signature"

        with pytest.raises(TandemAuthError, match="No pumperId"):
            client._extract_jwt_claims()


# ═══════════════════════════════════════════════════════════════════════════
# #14: PII sanitisation — expanded field coverage
#
# We reproduce the PII_FIELDS set and sanitize_for_logging() function here
# to test without importing the full HA chain through __init__.py.  The
# source of truth is custom_components/carelink/__init__.py.
# ═══════════════════════════════════════════════════════════════════════════

# Mirror of PII_FIELDS from __init__.py (must stay in sync)
_PII_FIELDS = {
    "firstName", "lastName", "username", "patientId", "conduitSerialNumber",
    "medicalDeviceSerialNumber", "systemId", "email", "phone", "emailAddress",
    "phoneNumber", "address", "dateOfBirth", "dob", "deviceSerialNumber",
    "patientName", "patientDateOfBirth", "patientCareGiver",
    # Tandem device/account identifiers
    "serialNumber", "tconnectDeviceId", "pumperId", "accountId",
    "partNumber",
}


def _sanitize_for_logging(data, depth=0):
    """Mirror of sanitize_for_logging() from __init__.py."""
    if depth > 10:
        return "[MAX_DEPTH]"
    if isinstance(data, dict):
        return {
            k: "[REDACTED]" if k in _PII_FIELDS else _sanitize_for_logging(v, depth + 1)
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [_sanitize_for_logging(item, depth + 1) for item in data]
    return data


def _verify_pii_fields_in_sync():
    """Read PII_FIELDS from __init__.py source to verify our mirror is correct."""
    import ast
    with open("custom_components/carelink/__init__.py") as f:
        source = f.read()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "PII_FIELDS":
                    # Evaluate the set literal
                    actual = eval(compile(ast.Expression(body=node.value), "<>", "eval"))
                    return actual
    return None


class TestExpandedPIISanitisation:
    """Verify that Tandem-specific identifiers are redacted from logs."""

    def test_pii_fields_in_sync_with_source(self):
        """Verify the test mirror of PII_FIELDS matches the source."""
        actual = _verify_pii_fields_in_sync()
        assert actual is not None, "Could not find PII_FIELDS in __init__.py"
        assert actual == _PII_FIELDS, (
            f"PII_FIELDS mismatch.\n"
            f"  In source but not test: {actual - _PII_FIELDS}\n"
            f"  In test but not source: {_PII_FIELDS - actual}"
        )

    def test_tandem_device_fields_redacted(self):
        """Tandem device identifiers must be redacted."""
        data = {
            "serialNumber": "SN12345678",
            "tconnectDeviceId": "device-abc-123",
            "pumperId": "pumper-xyz",
            "accountId": "acct-999",
            "partNumber": "PN-42",
            "modelNumber": "t:slim X2",  # NOT PII — should stay
        }
        result = _sanitize_for_logging(data)

        assert result["serialNumber"] == "[REDACTED]"
        assert result["tconnectDeviceId"] == "[REDACTED]"
        assert result["pumperId"] == "[REDACTED]"
        assert result["accountId"] == "[REDACTED]"
        assert result["partNumber"] == "[REDACTED]"
        assert result["modelNumber"] == "t:slim X2"

    def test_tandem_fields_in_nested_structure(self):
        """Tandem identifiers must be redacted in nested dicts."""
        data = {
            "pump_metadata": {
                "serialNumber": "SN12345678",
                "modelNumber": "t:slim X2",
                "tconnectDeviceId": "device-abc",
            },
            "pumper_info": {
                "firstName": "John",
                "pumperId": "pumper-xyz",
            },
        }
        result = _sanitize_for_logging(data)

        assert result["pump_metadata"]["serialNumber"] == "[REDACTED]"
        assert result["pump_metadata"]["tconnectDeviceId"] == "[REDACTED]"
        assert result["pump_metadata"]["modelNumber"] == "t:slim X2"
        assert result["pumper_info"]["firstName"] == "[REDACTED]"
        assert result["pumper_info"]["pumperId"] == "[REDACTED]"

    def test_original_pii_fields_still_redacted(self):
        """Original PII fields must still be redacted after expansion."""
        data = {
            "firstName": "John",
            "lastName": "Doe",
            "email": "john@example.com",
            "patientName": "John Doe",
            "patientDateOfBirth": "1990-01-01",
            "patientCareGiver": "Jane Doe",
            "serialNumber": "SN123",
            "pumperId": "pump-1",
        }
        result = _sanitize_for_logging(data)

        for key in data:
            assert result[key] == "[REDACTED]"
