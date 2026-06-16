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
