"""Built-in tool implementations.

All built-in tools are safe: no network calls, no filesystem access,
no arbitrary code execution. The calculator uses ast.parse to restrict
evaluation to literal arithmetic — it rejects any non-numeric AST nodes.
"""

from __future__ import annotations

import ast
import operator as op
from typing import Any

from app.runtime.errors import ToolArgValidationError
from app.runtime.registry import RegisteredTool, ToolRegistry

# ---------------------------------------------------------------------------
# Calculator
# ---------------------------------------------------------------------------

CALCULATOR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "expression": {
            "type": "string",
            "description": "A simple arithmetic expression, e.g. '2 + 3 * 4'",
        }
    },
    "required": ["expression"],
    "additionalProperties": False,
}

_BINARY_OPS: dict[type[ast.operator], Any] = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.Pow: op.pow,
    ast.Mod: op.mod,
    ast.FloorDiv: op.floordiv,
}

_UNARY_OPS: dict[type[ast.unaryop], Any] = {
    ast.USub: op.neg,
    ast.UAdd: op.pos,
}


def _safe_eval(node: ast.expr) -> float:
    """Recursively evaluate an arithmetic AST, rejecting non-arithmetic nodes.

    Only Constant (numeric), BinOp, and UnaryOp are allowed. Any Name, Call,
    Attribute, or other node raises ToolArgValidationError — this prevents
    __import__, open(), variable references, and similar injection attempts.
    """
    match node:
        case ast.Constant(value=v) if isinstance(v, (int, float)):
            return float(v)
        case ast.BinOp(left=left, op=op_node, right=right):
            fn = _BINARY_OPS.get(type(op_node))
            if fn is None:
                raise ToolArgValidationError(
                    f"Unsupported binary operator: {type(op_node).__name__}"
                )
            # operator module functions return Any; cast to float for strict mypy
            return float(fn(_safe_eval(left), _safe_eval(right)))
        case ast.UnaryOp(op=op_node, operand=operand):
            fn = _UNARY_OPS.get(type(op_node))
            if fn is None:
                raise ToolArgValidationError(
                    f"Unsupported unary operator: {type(op_node).__name__}"
                )
            return float(fn(_safe_eval(operand)))
        case _:
            raise ToolArgValidationError(
                f"Unsafe expression: {type(node).__name__} nodes are not allowed"
            )


async def calculator(args: dict[str, Any]) -> dict[str, Any]:
    expression: str = args["expression"]
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ToolArgValidationError(f"Invalid expression syntax: {exc}") from exc
    try:
        result = _safe_eval(tree.body)
    except ZeroDivisionError:
        raise ToolArgValidationError("Division by zero") from None
    except OverflowError:
        raise ToolArgValidationError("Arithmetic overflow: result is too large") from None
    return {"result": result, "expression": expression}


CALCULATOR_TOOL = RegisteredTool(
    name="calculator",
    description="Evaluates a simple arithmetic expression (+, -, *, /, **, %, //).",
    json_schema=CALCULATOR_SCHEMA,
    impl_fn=calculator,
)


def register_builtins(registry: ToolRegistry) -> None:
    """Register all built-in tools into the registry.

    Call this before compiling any graph so builtins are always available.
    """
    registry.register(CALCULATOR_TOOL)
