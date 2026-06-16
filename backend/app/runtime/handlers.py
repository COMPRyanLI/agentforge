"""Node handler factories for the agent runtime.

Each factory returns a coroutine that takes RunState and returns a partial
state update dict (LangGraph merges it). Handlers are pure closures: the
LLMProvider and ToolRegistry are bound at compile time, never looked up
at runtime. This is the key replay-safety guarantee.

Replay-safety rules (enforced here):
- No datetime.now(), random, or uuid4() calls inside any handler.
- step_index is incremented explicitly in state (not derived from LangGraph
  internals) so it survives checkpointing and remains stable on replay.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from app.llm.provider import LLMProvider
from app.runtime.errors import AgentRuntimeError
from app.runtime.registry import ToolRegistry, invoke_tool
from app.runtime.state import Message, RunState

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 10

NodeHandler = Callable[[RunState], Awaitable[dict[str, Any]]]


def make_input_handler() -> NodeHandler:
    """Input node: passthrough.

    The user message is already placed in state["messages"] by the executor
    before graph invocation, so this node is a no-op. It exists as an explicit
    entry point so the graph structure mirrors the canvas node layout.
    """

    async def _handler(state: RunState) -> dict[str, Any]:
        return {}

    return _handler


def make_llm_handler(
    llm: LLMProvider,
    registry: ToolRegistry,
    tool_names: list[str],
    system_prompt: str,
) -> NodeHandler:
    """LLM node with an internal tool-calling loop.

    Calls the LLM, and if it returns tool_calls, invokes each tool, appends
    the results to messages, and calls the LLM again — up to MAX_TOOL_ITERATIONS
    times. Once the LLM returns plain content, the loop ends.

    The loop is intentionally contained inside this node for Phase 2 simplicity.
    Phase 4 will checkpoint each LLM call and tool invocation as discrete steps.
    """
    tool_schemas = registry.to_llm_schemas(tool_names) if tool_names else None

    async def _handler(state: RunState) -> dict[str, Any]:
        messages: list[Message] = list(state["messages"])

        # Prepend system message if absent. Explicit Message annotation ensures
        # the concat result is list[Message] (not list[dict[str, str]]).
        if not messages or messages[0].get("role") != "system":
            sys_msg: Message = {"role": "system", "content": system_prompt}
            messages = [sys_msg] + messages

        for _ in range(MAX_TOOL_ITERATIONS):
            response = await llm.chat(messages, tools=tool_schemas)

            if not response.tool_calls:
                text_msg: Message = {"role": "assistant", "content": response.content}
                messages.append(text_msg)
                break

            # Build the assistant's tool-call turn in Ollama native format
            assistant_msg: Message = {
                "role": "assistant",
                "content": response.content,
                "tool_calls": [
                    {
                        "function": {
                            "name": tc.name,
                            "arguments": tc.arguments,
                        }
                    }
                    for tc in response.tool_calls
                ],
            }
            messages.append(assistant_msg)

            # Invoke each tool and append results
            for tc in response.tool_calls:
                result = await invoke_tool(registry, tc.name, tc.arguments)
                tool_msg: Message = {
                    "role": "tool",
                    "name": tc.name,
                    "content": str(result),
                }
                messages.append(tool_msg)
        else:
            # Exceeded MAX_TOOL_ITERATIONS without a final text response
            logger.warning(
                "run_id=%s llm node hit MAX_TOOL_ITERATIONS (%d)",
                state["run_id"],
                MAX_TOOL_ITERATIONS,
            )

        return {
            "messages": messages,
            "step_index": state["step_index"] + 1,
        }

    return _handler


def make_tool_handler(
    registry: ToolRegistry,
    tool_name: str,
) -> NodeHandler:
    """Standalone tool node for explicit tool invocations wired in graph_json.

    Extracts the args for `tool_name` from the most recent assistant message's
    tool_calls list, invokes the tool, and appends the result to messages.
    """

    async def _handler(state: RunState) -> dict[str, Any]:
        messages: list[Message] = list(state["messages"])

        # Find the most recent assistant message with a matching tool call
        args: dict[str, Any] | None = None
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                for tc in msg.get("tool_calls", []):
                    if tc.get("function", {}).get("name") == tool_name:
                        args = tc["function"].get("arguments", {})
                        break
                break

        if args is None:
            raise AgentRuntimeError(
                f"Tool node '{tool_name}': no matching tool call found in message history"
            )

        result = await invoke_tool(registry, tool_name, args)
        messages.append(
            {
                "role": "tool",
                "name": tool_name,
                "content": str(result),
            }
        )
        return {
            "messages": messages,
            "step_index": state["step_index"] + 1,
        }

    return _handler


def make_output_handler() -> NodeHandler:
    """Output node: extracts the final assistant answer from messages."""

    async def _handler(state: RunState) -> dict[str, Any]:
        for msg in reversed(state["messages"]):
            if msg.get("role") == "assistant" and msg.get("content"):
                return {"output": msg["content"]}
        return {"output": None}

    return _handler
