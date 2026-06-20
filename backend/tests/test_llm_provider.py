"""Unit tests for OllamaProvider.

The ollama AsyncClient is mocked so these run in CI without a live Ollama server.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from app.llm.provider import LLMResponse, OllamaProvider, ToolCall


def _make_mock_client(
    msg: MagicMock,
    *,
    prompt_eval_count: int | None = None,
    eval_count: int | None = None,
    total_duration: int | None = None,
) -> AsyncMock:
    """Return a mock AsyncClient whose .chat() resolves to a response with msg."""
    mock_resp = MagicMock()
    mock_resp.message = msg
    mock_resp.prompt_eval_count = prompt_eval_count
    mock_resp.eval_count = eval_count
    mock_resp.total_duration = total_duration
    mock_client = AsyncMock()
    mock_client.chat.return_value = mock_resp
    return mock_client


def _text_msg(content: str) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = None
    return msg


def _tool_msg(calls: list[tuple[str, dict[str, Any]]]) -> MagicMock:
    """Build a mock message carrying tool_calls."""
    tool_calls = []
    for name, args in calls:
        fn = MagicMock()
        fn.name = name
        fn.arguments = args
        tc = MagicMock()
        tc.function = fn
        tool_calls.append(tc)
    msg = MagicMock()
    msg.content = None
    msg.tool_calls = tool_calls
    return msg


async def test_plain_text_response() -> None:
    mock_client = _make_mock_client(_text_msg("Paris is the capital of France."))

    with patch("app.llm.provider.AsyncClient") as MockAsyncClient:
        MockAsyncClient.return_value = mock_client
        provider = OllamaProvider("http://localhost:11434", "gemma4:e4b")
        result = await provider.chat([{"role": "user", "content": "Capital of France?"}])

    assert isinstance(result, LLMResponse)
    assert result.content == "Paris is the capital of France."
    assert result.tool_calls == []


async def test_single_tool_call() -> None:
    mock_client = _make_mock_client(_tool_msg([("get_weather", {"city": "Tokyo"})]))

    with patch("app.llm.provider.AsyncClient") as MockAsyncClient:
        MockAsyncClient.return_value = mock_client
        provider = OllamaProvider("http://localhost:11434", "gemma4:e4b")
        result = await provider.chat(
            [{"role": "user", "content": "Weather in Tokyo?"}],
            tools=[{"type": "function", "function": {"name": "get_weather"}}],
        )

    assert result.content is None
    assert len(result.tool_calls) == 1
    tc = result.tool_calls[0]
    assert isinstance(tc, ToolCall)
    assert tc.name == "get_weather"
    assert tc.arguments == {"city": "Tokyo"}


async def test_multiple_tool_calls() -> None:
    mock_client = _make_mock_client(
        _tool_msg(
            [
                ("get_weather", {"city": "Tokyo"}),
                ("get_weather", {"city": "London"}),
            ]
        )
    )

    with patch("app.llm.provider.AsyncClient") as MockAsyncClient:
        MockAsyncClient.return_value = mock_client
        provider = OllamaProvider("http://localhost:11434", "gemma4:e4b")
        result = await provider.chat(
            [{"role": "user", "content": "Compare Tokyo and London weather."}]
        )

    assert len(result.tool_calls) == 2
    assert result.tool_calls[0].name == "get_weather"
    assert result.tool_calls[1].arguments == {"city": "London"}


async def test_empty_tool_calls_list_treated_as_no_calls() -> None:
    msg = MagicMock()
    msg.content = "I don't know."
    msg.tool_calls = []
    mock_client = _make_mock_client(msg)

    with patch("app.llm.provider.AsyncClient") as MockAsyncClient:
        MockAsyncClient.return_value = mock_client
        provider = OllamaProvider("http://localhost:11434", "gemma4:e4b")
        result = await provider.chat([{"role": "user", "content": "?"}])

    assert result.tool_calls == []


async def test_passes_tools_to_client() -> None:
    mock_client = _make_mock_client(_text_msg("ok"))
    tools = [{"type": "function", "function": {"name": "calc"}}]

    with patch("app.llm.provider.AsyncClient") as MockAsyncClient:
        MockAsyncClient.return_value = mock_client
        provider = OllamaProvider("http://localhost:11434", "gemma4:e4b")
        await provider.chat([{"role": "user", "content": "2+2"}], tools=tools)

    mock_client.chat.assert_awaited_once_with(
        model="gemma4:e4b",
        messages=[{"role": "user", "content": "2+2"}],
        tools=tools,
    )


async def test_captures_token_and_latency_usage() -> None:
    mock_client = _make_mock_client(
        _text_msg("ok"),
        prompt_eval_count=12,
        eval_count=34,
        total_duration=2_500_000_000,  # 2.5s in nanoseconds
    )

    with patch("app.llm.provider.AsyncClient") as MockAsyncClient:
        MockAsyncClient.return_value = mock_client
        provider = OllamaProvider("http://localhost:11434", "gemma4:e4b")
        result = await provider.chat([{"role": "user", "content": "hi"}])

    assert result.prompt_tokens == 12
    assert result.completion_tokens == 34
    assert result.total_duration_ms == 2500.0


async def test_usage_fields_are_none_when_client_omits_them() -> None:
    mock_client = _make_mock_client(_text_msg("ok"))  # all usage kwargs default to None

    with patch("app.llm.provider.AsyncClient") as MockAsyncClient:
        MockAsyncClient.return_value = mock_client
        provider = OllamaProvider("http://localhost:11434", "gemma4:e4b")
        result = await provider.chat([{"role": "user", "content": "hi"}])

    assert result.prompt_tokens is None
    assert result.completion_tokens is None
    assert result.total_duration_ms is None
