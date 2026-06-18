"""Unit tests for the HTTP tool executor: requests, SSRF guards, size cap."""

from __future__ import annotations

import json
import socket
from typing import Any

import httpx
import pytest

import app.runtime.http_tool as http_tool_module
from app.models.tool import Tool
from app.runtime.errors import ToolExecutionError
from app.runtime.http_tool import make_http_tool, parse_http_tool_config

_PUBLIC_ADDRINFO = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


def _make_tool(config_json: dict[str, Any], json_schema: dict[str, Any] | None = None) -> Tool:
    tool = Tool(
        owner_id=None,  # type: ignore[arg-type]
        name="weather",
        description="test tool",
        json_schema=json_schema or {"type": "object", "properties": {}},
        impl_type="http",
        config_json=config_json,
    )
    return tool


def _patch_public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_resolve(host: str, port: int) -> list[tuple[Any, ...]]:
        return _PUBLIC_ADDRINFO

    monkeypatch.setattr(http_tool_module, "_resolve", _fake_resolve)


def _patch_transport(monkeypatch: pytest.MonkeyPatch, handler: Any) -> None:
    def _fake_make_client(timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.MockTransport(handler), follow_redirects=False, timeout=timeout
        )

    monkeypatch.setattr(http_tool_module, "_make_client", _fake_make_client)


def test_parse_config_rejects_missing_url() -> None:
    with pytest.raises(ToolExecutionError, match="url"):
        parse_http_tool_config({})


def test_parse_config_rejects_bad_method() -> None:
    with pytest.raises(ToolExecutionError, match="method"):
        parse_http_tool_config({"url": "https://example.com", "method": "TRACE"})


async def test_get_request_sends_args_as_query_params(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["query"] = str(request.url.params)
        return httpx.Response(200, json={"temp": 72})

    _patch_public_dns(monkeypatch)
    _patch_transport(monkeypatch, handler)

    tool = _make_tool({"url": "https://example.com/weather", "method": "GET"})
    registered = make_http_tool(tool)
    result = await registered.impl_fn({"city": "nyc"})

    assert result == {"temp": 72}
    assert "city=nyc" in captured["query"]


async def test_post_request_sends_args_as_json_body(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True})

    _patch_public_dns(monkeypatch)
    _patch_transport(monkeypatch, handler)

    tool = _make_tool({"url": "https://example.com/submit", "method": "POST"})
    registered = make_http_tool(tool)
    result = await registered.impl_fn({"name": "alice"})

    assert result == {"ok": True}
    assert captured["body"] == {"name": "alice"}


async def test_non_2xx_raises_tool_execution_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    _patch_public_dns(monkeypatch)
    _patch_transport(monkeypatch, handler)

    tool = _make_tool({"url": "https://example.com/fail", "method": "GET"})
    registered = make_http_tool(tool)
    with pytest.raises(ToolExecutionError, match="500"):
        await registered.impl_fn({})


async def test_http_url_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_public_dns(monkeypatch)
    tool = _make_tool({"url": "http://example.com/insecure", "method": "GET"})
    registered = make_http_tool(tool)
    with pytest.raises(ToolExecutionError, match="https"):
        await registered.impl_fn({})


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "10.0.0.5",
        "192.168.1.1",
        "169.254.169.254",
    ],
)
async def test_private_or_metadata_ip_rejected(monkeypatch: pytest.MonkeyPatch, ip: str) -> None:
    async def _fake_resolve(host: str, port: int) -> list[tuple[Any, ...]]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))]

    monkeypatch.setattr(http_tool_module, "_resolve", _fake_resolve)

    tool = _make_tool({"url": "https://attacker-controlled.example/x", "method": "GET"})
    registered = make_http_tool(tool)
    with pytest.raises(ToolExecutionError, match="private|loopback|link-local|reserved"):
        await registered.impl_fn({})


async def test_redirect_not_followed(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "https://internal.example/secret"})

    _patch_public_dns(monkeypatch)
    _patch_transport(monkeypatch, handler)

    tool = _make_tool({"url": "https://example.com/redirector", "method": "GET"})
    registered = make_http_tool(tool)
    with pytest.raises(ToolExecutionError, match="redirect"):
        await registered.impl_fn({})


async def test_oversized_response_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    big_body = b"x" * (1024 * 1024 + 1)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=big_body)

    _patch_public_dns(monkeypatch)
    _patch_transport(monkeypatch, handler)

    tool = _make_tool({"url": "https://example.com/huge", "method": "GET"})
    registered = make_http_tool(tool)
    with pytest.raises(ToolExecutionError, match="byte limit"):
        await registered.impl_fn({})


async def test_request_is_pinned_to_the_validated_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    """The connection must target the exact IP that was validated, not a
    hostname httpx would re-resolve independently — otherwise the IP check
    is advisory only and DNS rebinding (a different IP at connect-time)
    bypasses it entirely."""
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["host"] = request.url.host
        captured["host_header"] = request.headers.get("host")
        captured["sni"] = request.extensions.get("sni_hostname")
        return httpx.Response(200, json={"ok": True})

    _patch_public_dns(monkeypatch)
    _patch_transport(monkeypatch, handler)

    tool = _make_tool({"url": "https://example.com/weather", "method": "GET"})
    registered = make_http_tool(tool)
    await registered.impl_fn({})

    assert captured["host"] == "93.184.216.34"
    assert captured["host_header"] == "example.com"
    assert captured["sni"] == "example.com"


async def test_dns_rebinding_does_not_bypass_the_ip_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate the classic rebinding attack: the resolver returns a public
    IP (so the IP check passes), but if the real connection re-resolved the
    hostname independently and got a private IP, the request would have
    silently reached an internal address. Assert the transport never even
    sees that private IP — i.e. the request is built against the IP that
    was actually validated, with no second resolution in between."""
    resolve_calls = 0

    async def _rebinding_resolve(host: str, port: int) -> list[tuple[Any, ...]]:
        nonlocal resolve_calls
        resolve_calls += 1
        # A real rebinding DNS server would answer differently on a second
        # query; if this module resolved twice, the second answer (private)
        # would be the one that mattered.
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 443))]

    monkeypatch.setattr(http_tool_module, "_resolve", _rebinding_resolve)

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("transport should never be reached: IP check must reject first")

    _patch_transport(monkeypatch, handler)

    tool = _make_tool({"url": "https://attacker-controlled.example/x", "method": "GET"})
    registered = make_http_tool(tool)
    with pytest.raises(ToolExecutionError, match="private|loopback|link-local|reserved"):
        await registered.impl_fn({})

    # Resolved exactly once — there is no second, independent resolution at
    # connect time for httpx to be tricked by.
    assert resolve_calls == 1


async def test_timeout_raises_tool_execution_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out")

    _patch_public_dns(monkeypatch)
    _patch_transport(monkeypatch, handler)

    tool = _make_tool({"url": "https://example.com/slow", "method": "GET"})
    registered = make_http_tool(tool)
    with pytest.raises(ToolExecutionError, match="timed out"):
        await registered.impl_fn({})
