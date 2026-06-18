"""Runtime exception hierarchy.

No imports from other runtime modules — this file is the base layer.
"""


class AgentRuntimeError(Exception):
    """Base for all expected runtime failures (model errors, tool errors, bad graph)."""


class GraphCompilationError(AgentRuntimeError):
    """Raised when graph_json cannot be compiled into a valid StateGraph."""


class ToolArgValidationError(AgentRuntimeError):
    """Raised when tool arguments fail JSON Schema validation."""


class ToolNotFoundError(AgentRuntimeError):
    """Raised when a tool name is not registered in the ToolRegistry."""


class ToolExecutionError(AgentRuntimeError):
    """Raised when a tool's implementation raises during invocation."""


class ToolCallAmbiguousError(AgentRuntimeError):
    """Raised when a tool_calls row for an idempotency key is stuck "pending".

    This means a prior attempt called the tool and the process crashed before
    recording whether it succeeded — whether the side effect actually fired is
    unknown. Re-invoking could double-fire it, so this is treated as a
    permanent failure requiring manual verification of the external system's
    state, not an automatic retry.
    """
