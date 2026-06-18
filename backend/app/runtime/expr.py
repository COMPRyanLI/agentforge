"""Safe boolean-expression evaluator for `condition`/`loop` node `data.expr`.

Same AST-whitelist technique as app/runtime/builtins.py's calculator: parse with
ast.parse(mode="eval") and recursively evaluate only a fixed set of node types,
rejecting everything else (Call, real attribute/method access, imports, etc.)
before it can ever execute.

Supported expression surface (this is the REAL surface, not the
`state.score > 0.5` shorthand PLAN.md's illustrative example uses):

- Names resolved against a fixed namespace: `output`, `last_tool_result`,
  `step_index` (see `build_namespace`).
- Comparisons: <, >, <=, >=, ==, !=, in, not in
- Boolean combinators: and, or, not
- Constants: str, int, float, bool, None
- Read-only dict-key access on a Name (or on the result of another dict-key
  access) via dot or bracket syntax: `last_tool_result.score`,
  `last_tool_result["score"]`, `last_tool_result.scores.avg`. This is NOT
  Python attribute access — `expr.attr` is implemented as `dict.get("attr")`
  on the evaluated dict, so it can only ever read a key, never call a method
  or reach an object's real `__dict__`. Accessing a key that doesn't exist
  or attribute-accessing a non-dict returns None rather than raising, so a
  condition over an absent field is just falsy instead of crashing the run.

`last_tool_result` is the most recent tool message's content, json.loads'd
into a dict when it parses as one (so `.score`-style access works against
typical builtin/HTTP tool results), otherwise left as the raw string (so
`'error' in last_tool_result`-style string checks still work).
"""

from __future__ import annotations

import ast
import json
import operator as op
from typing import Any

from app.runtime.errors import AgentRuntimeError
from app.runtime.state import RunState

_COMPARE_OPS: dict[type[ast.cmpop], Any] = {
    ast.Lt: op.lt,
    ast.Gt: op.gt,
    ast.LtE: op.le,
    ast.GtE: op.ge,
    ast.Eq: op.eq,
    ast.NotEq: op.ne,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}


class ExprEvaluationError(AgentRuntimeError):
    """Raised when a condition/loop `data.expr` is unsafe or fails to evaluate."""


def build_namespace(
    output: str | None,
    last_tool_result_raw: str | None,
    step_index: int,
) -> dict[str, Any]:
    """Build the fixed namespace exposed to condition/loop expressions."""
    last_tool_result: Any = None
    if last_tool_result_raw is not None:
        try:
            last_tool_result = json.loads(last_tool_result_raw)
        except (json.JSONDecodeError, ValueError):
            last_tool_result = last_tool_result_raw
    return {
        "output": output,
        "last_tool_result": last_tool_result,
        "step_index": step_index,
    }


def namespace_from_state(state: RunState) -> dict[str, Any]:
    """Derive the condition/loop namespace from the live RunState.

    Scans messages once, newest-first, for the last assistant `output` and the
    last tool result — both are pure reads of already-checkpointed state, so
    this is deterministic and safe to recompute on replay.
    """
    output: str | None = None
    last_tool_result_raw: str | None = None
    for msg in reversed(state["messages"]):
        role = msg.get("role")
        if output is None and role == "assistant" and msg.get("content"):
            output = msg["content"]
        if last_tool_result_raw is None and role == "tool":
            last_tool_result_raw = msg.get("content")
        if output is not None and last_tool_result_raw is not None:
            break
    return build_namespace(output, last_tool_result_raw, state["step_index"])


def _dict_key_lookup(value: Any, key: Any) -> Any:
    if not isinstance(value, dict):
        raise ExprEvaluationError(
            f"Cannot access key {key!r}: value is not a dict (got {type(value).__name__})"
        )
    return value.get(key)


def _eval(node: ast.expr, namespace: dict[str, Any]) -> Any:
    match node:
        case ast.Constant(value=v):
            return v
        case ast.Name(id=name):
            if name not in namespace:
                raise ExprEvaluationError(f"Unknown name: {name!r}")
            return namespace[name]
        case ast.Attribute(value=value, attr=attr):
            return _dict_key_lookup(_eval(value, namespace), attr)
        case ast.Subscript(value=value, slice=slice_node):
            return _dict_key_lookup(_eval(value, namespace), _eval(slice_node, namespace))
        case ast.UnaryOp(op=ast.Not(), operand=operand):
            return not _eval(operand, namespace)
        case ast.BoolOp(op=bool_op, values=values):
            evaluated = [_eval(v, namespace) for v in values]
            if isinstance(bool_op, ast.And):
                return all(evaluated)
            return any(evaluated)
        case ast.Compare(left=left, ops=ops, comparators=comparators):
            current = _eval(left, namespace)
            for op_node, comparator in zip(ops, comparators, strict=True):
                fn = _COMPARE_OPS.get(type(op_node))
                if fn is None:
                    raise ExprEvaluationError(
                        f"Unsupported comparison operator: {type(op_node).__name__}"
                    )
                right = _eval(comparator, namespace)
                if not fn(current, right):
                    return False
                current = right
            return True
        case _:
            raise ExprEvaluationError(
                f"Unsafe expression: {type(node).__name__} nodes are not allowed"
            )


def evaluate_condition(expr: str, namespace: dict[str, Any]) -> bool:
    """Parse and safely evaluate a condition/loop `data.expr` string to a bool."""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ExprEvaluationError(f"Invalid expression syntax: {exc}") from exc
    return bool(_eval(tree.body, namespace))
