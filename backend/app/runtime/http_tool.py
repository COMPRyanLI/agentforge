"""HTTP tool executor: turns a DB `Tool` row with impl_type=="http" into a
RegisteredTool that actually performs an HTTP call.

SSRF protection: `tool.config_json["url"]` is data a user typed into the
tool-builder UI, then later invoked by name from inside a graph run — the
server makes the request, not the user's browser. That's the textbook
SSRF-via-webhook-tool shape (an attacker registers a "tool" pointing at
http://169.254.169.254/... or an internal service, then tricks/waits for an
agent to call it), so every request through this module is restricted to:
https only, no following redirects, the resolved IP checked against
private/loopback/link-local/multicast/reserved ranges (not just the hostname
string, since a hostname can resolve to a blocked address via DNS rebinding),
and a capped response size so a malicious or misbehaving endpoint can't feed
unbounded data back into the LLM's context.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import socket
from dataclasses import dataclass
from typing import Any

import httpx

from app.models.tool import Tool
from app.runtime.errors import ToolExecutionError
from app.runtime.registry import RegisteredTool

_ALLOWED_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})
_MAX_RESPONSE_BYTES = 1024 * 1024  # 1 MiB
_DEFAULT_TIMEOUT_SECONDS = 10.0


@dataclass(slots=True, frozen=True)
class HttpToolConfig:
    url: str
    method: str
    headers: dict[str, str] | None
    timeout_seconds: float


def parse_http_tool_config(config_json: dict[str, Any] | None) -> HttpToolConfig:
    config_json = config_json or {}
    url = config_json.get("url")
    if not isinstance(url, str) or not url:
        raise ToolExecutionError("HTTP tool config_json is missing a non-empty 'url'")

    method = str(config_json.get("method", "GET")).upper()
    if method not in _ALLOWED_METHODS:
        raise ToolExecutionError(
            f"HTTP tool config_json method must be one of {sorted(_ALLOWED_METHODS)}, "
            f"got {method!r}"
        )

    headers = config_json.get("headers")
    if headers is not None and not isinstance(headers, dict):
        raise ToolExecutionError("HTTP tool config_json 'headers' must be an object")

    timeout = config_json.get("timeout_seconds", _DEFAULT_TIMEOUT_SECONDS)
    return HttpToolConfig(url=url, method=method, headers=headers, timeout_seconds=float(timeout))


async def _resolve(host: str, port: int) -> list[tuple[Any, ...]]:
    """Thin wrapper so tests can monkeypatch DNS resolution without touching
    the network or a real event loop's resolver."""
    return await asyncio.get_running_loop().getaddrinfo(host, port)


async def _validate_url(url: str) -> None:
    """https-only, and the resolved IP (not just the hostname string) must
    not fall in a private/loopback/link-local/multicast/reserved range."""
    parsed = httpx.URL(url)
    if parsed.scheme != "https":
        raise ToolExecutionError(f"HTTP tool URL must use https, got scheme {parsed.scheme!r}")

    host = parsed.host
    port = parsed.port or 443
    try:
        addrinfo = await _resolve(host, port)
    except socket.gaierror as exc:
        raise ToolExecutionError(
            f"HTTP tool URL host {host!r} could not be resolved: {exc}"
        ) from exc

    for _family, _type, _proto, _canonname, sockaddr in addrinfo:
        ip = ipaddress.ip_address(sockaddr[0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local  # covers the 169.254.169.254 cloud metadata address
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ToolExecutionError(
                f"HTTP tool URL host {host!r} resolves to {ip}, which is a private/"
                "loopback/link-local/multicast/reserved address — refusing to "
                "avoid a server-side request forgery"
            )


def _make_client(timeout: float) -> httpx.AsyncClient:
    """Thin wrapper so tests can monkeypatch in a MockTransport without
    reaching the network."""
    return httpx.AsyncClient(follow_redirects=False, timeout=timeout)


def make_http_tool(tool: Tool) -> RegisteredTool:
    config = parse_http_tool_config(tool.config_json)

    async def _impl(args: dict[str, Any]) -> dict[str, Any]:
        await _validate_url(config.url)

        params = args if config.method in ("GET", "DELETE") else None
        json_body = args if config.method not in ("GET", "DELETE") else None

        try:
            async with (
                _make_client(config.timeout_seconds) as client,
                client.stream(
                    config.method,
                    config.url,
                    params=params,
                    json=json_body,
                    headers=config.headers,
                ) as response,
            ):
                if response.is_redirect:
                    raise ToolExecutionError(
                        f"HTTP tool received a {response.status_code} redirect; "
                        "redirects are not followed"
                    )
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > _MAX_RESPONSE_BYTES:
                        raise ToolExecutionError(
                            f"HTTP tool response exceeded the {_MAX_RESPONSE_BYTES}-byte limit"
                        )
                    chunks.append(chunk)
                body = b"".join(chunks)
                if not response.is_success:
                    raise ToolExecutionError(
                        f"HTTP tool received {response.status_code}: {body[:200]!r}"
                    )
        except httpx.TimeoutException as exc:
            raise ToolExecutionError(f"HTTP tool request timed out: {exc}") from exc
        except httpx.HTTPError as exc:
            raise ToolExecutionError(f"HTTP tool request failed: {exc}") from exc

        try:
            parsed: Any = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {"body": body.decode("utf-8", errors="replace")}
        return parsed if isinstance(parsed, dict) else {"result": parsed}

    return RegisteredTool(
        name=tool.name,
        description=tool.description or "",
        json_schema=tool.json_schema,
        impl_fn=_impl,
    )
