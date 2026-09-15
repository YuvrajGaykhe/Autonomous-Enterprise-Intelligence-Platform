"""
Security constraints for Layer 1 source access (spec Section 14).

Outbound HTTP (Odoo mock and Generic REST connectors):

    validate_base_url      an http or https URL with a host and a port from 1 to
                           65535 if one is given, and no embedded credentials,
                           query string, fragment, whitespace or control
                           characters
    validate_request_path  a configured endpoint path that stays relative to
                           base_url: one leading "/", no "..", query or fragment
    validate_timeout       finite seconds, greater than 0 and at most
                           MAX_TIMEOUT_SECONDS
    read_only_client       an httpx.Client that sends GET requests only, only to
                           base_url's scheme, host and port, and never follows
                           redirects

Validation keeps accidental requests away from unintended hosts; the client
enforces the read-only, same-origin rule on every request, so a code path
that bypasses configuration validation still cannot write to a source or
reach another host.

Rejection messages name the broken rule, never the offending value: URLs can
embed credentials, and these messages reach command output and exception
chains.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

import httpx

ALLOWED_SCHEMES = frozenset({"http", "https"})
ALLOWED_METHOD = "GET"
MIN_PORT = 1
MAX_PORT = 65535
MAX_TIMEOUT_SECONDS = 300.0


class SecurityConstraintError(Exception):
    """A Layer 1 security constraint was violated."""


class UnsafeConfigurationError(SecurityConstraintError, ValueError):
    """A configuration value breaks a security rule."""


class OutboundRequestRefused(SecurityConstraintError):
    """A connector tried to send a request the read-only client does not allow."""


def _has_whitespace_or_control(value: str) -> bool:
    return any(char.isspace() or not char.isprintable() for char in value)


def validate_base_url(value: object) -> str:
    """Return value if it is a safe source base URL.

    Raises:
        UnsafeConfigurationError: the value breaks a rule listed in the module docstring.
    """
    if not isinstance(value, str) or not value:
        raise UnsafeConfigurationError("must be a non-empty string")
    if _has_whitespace_or_control(value):
        raise UnsafeConfigurationError("must not contain whitespace or control characters")
    try:
        url = httpx.URL(value)
    except httpx.InvalidURL:
        raise UnsafeConfigurationError("is not a valid URL") from None
    if url.scheme not in ALLOWED_SCHEMES:
        raise UnsafeConfigurationError("must be an http or https URL")
    if not url.host:
        raise UnsafeConfigurationError("must include a host")
    if url.port is not None and not MIN_PORT <= url.port <= MAX_PORT:
        raise UnsafeConfigurationError(f"must use a port from {MIN_PORT} to {MAX_PORT}")
    if url.userinfo:
        raise UnsafeConfigurationError(
            "must not embed credentials; supply them through environment variables")
    if "?" in value or "#" in value:
        raise UnsafeConfigurationError("must not include a query string or fragment")
    return value


def validate_request_path(value: object) -> str:
    """Return value if it is a safe endpoint path relative to base_url.

    Raises:
        UnsafeConfigurationError: the value breaks a rule listed in the module docstring.
    """
    if not isinstance(value, str) or not value:
        raise UnsafeConfigurationError("must be a non-empty string")
    if _has_whitespace_or_control(value):
        raise UnsafeConfigurationError("must not contain whitespace or control characters")
    if not value.startswith("/") or value.startswith("//"):
        raise UnsafeConfigurationError("must be a path starting with a single '/'")
    if "\\" in value:
        raise UnsafeConfigurationError("must not contain backslashes")
    if "?" in value or "#" in value:
        raise UnsafeConfigurationError("must not include a query string or fragment")
    if ".." in value.split("/"):
        raise UnsafeConfigurationError("must not contain '..' segments")
    return value


def validate_timeout(value: object) -> float:
    """The timeout in seconds: finite, greater than 0 and at most MAX_TIMEOUT_SECONDS.

    Numbers and numeric strings are accepted; booleans are not.

    Raises:
        UnsafeConfigurationError: the value is not an acceptable timeout.
    """
    message = f"must be a finite number of seconds greater than 0 and at most {MAX_TIMEOUT_SECONDS:g}"
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise UnsafeConfigurationError(message)
    try:
        seconds = float(value)
    except ValueError:
        raise UnsafeConfigurationError(message) from None
    if not math.isfinite(seconds) or seconds <= 0 or seconds > MAX_TIMEOUT_SECONDS:
        raise UnsafeConfigurationError(message)
    return seconds


def _origin(url: httpx.URL) -> tuple[str, str, int | None]:
    return url.scheme, url.host, url.port


def read_only_client(
    base_url: str,
    timeout: float,
    headers: Mapping[str, str] | None = None,
) -> httpx.Client:
    """An httpx.Client for one source: GET only, same origin only, no redirects.

    Every request is checked before it is sent; a refused request raises
    OutboundRequestRefused and never reaches the network.

    Raises:
        UnsafeConfigurationError: base_url or timeout is not acceptable.
    """
    origin = _origin(httpx.URL(validate_base_url(base_url)))
    seconds = validate_timeout(timeout)

    def refuse_unsafe_request(request: httpx.Request) -> None:
        if request.method != ALLOWED_METHOD:
            raise OutboundRequestRefused(
                f"{request.method} requests are not allowed; source connectors are read-only")
        if _origin(request.url) != origin:
            raise OutboundRequestRefused("request target is outside the configured base_url origin")

    return httpx.Client(
        base_url=base_url,
        timeout=seconds,
        headers=headers,
        follow_redirects=False,
        event_hooks={"request": [refuse_unsafe_request]},
    )
