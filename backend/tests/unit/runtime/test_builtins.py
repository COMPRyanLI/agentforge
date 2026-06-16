"""Unit tests for the calculator builtin."""

from __future__ import annotations

import pytest

from app.runtime.builtins import calculator, register_builtins
from app.runtime.errors import ToolArgValidationError
from app.runtime.registry import ToolRegistry

# ---------------------------------------------------------------------------
# Correctness
# ---------------------------------------------------------------------------


async def test_addition() -> None:
    result = await calculator({"expression": "2 + 2"})
    assert result["result"] == pytest.approx(4.0)
    assert result["expression"] == "2 + 2"


async def test_multiplication() -> None:
    result = await calculator({"expression": "6 * 7"})
    assert result["result"] == pytest.approx(42.0)


async def test_power() -> None:
    result = await calculator({"expression": "2 ** 10"})
    assert result["result"] == pytest.approx(1024.0)


async def test_division() -> None:
    result = await calculator({"expression": "10 / 4"})
    assert result["result"] == pytest.approx(2.5)


async def test_parentheses() -> None:
    result = await calculator({"expression": "(3 + 4) * 2"})
    assert result["result"] == pytest.approx(14.0)


async def test_unary_negation() -> None:
    result = await calculator({"expression": "-5"})
    assert result["result"] == pytest.approx(-5.0)


async def test_modulo() -> None:
    result = await calculator({"expression": "10 % 3"})
    assert result["result"] == pytest.approx(1.0)


async def test_floor_division() -> None:
    result = await calculator({"expression": "7 // 2"})
    assert result["result"] == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# Safety: must reject non-arithmetic nodes
# ---------------------------------------------------------------------------


async def test_rejects_name_node() -> None:
    """Variable references are rejected — no Name AST nodes allowed."""
    with pytest.raises(ToolArgValidationError, match="Name"):
        await calculator({"expression": "x + 1"})


async def test_rejects_function_call() -> None:
    """Function calls are rejected — blocks open(), __import__, etc."""
    with pytest.raises(ToolArgValidationError, match="Call"):
        await calculator({"expression": "open('secret')"})


async def test_rejects_dunder_import() -> None:
    """__import__ is a function call and must be rejected."""
    with pytest.raises(ToolArgValidationError, match="Call"):
        await calculator({"expression": "__import__('os')"})


async def test_rejects_attribute_access() -> None:
    """Attribute access is rejected — blocks os.system etc."""
    with pytest.raises(ToolArgValidationError, match="Attribute"):
        await calculator({"expression": "os.path"})


async def test_rejects_string_constant() -> None:
    """Only numeric constants are allowed."""
    with pytest.raises(ToolArgValidationError):
        await calculator({"expression": "'hello'"})


async def test_invalid_syntax_raises() -> None:
    with pytest.raises(ToolArgValidationError, match="syntax"):
        await calculator({"expression": "2 +"})


# ---------------------------------------------------------------------------
# register_builtins
# ---------------------------------------------------------------------------


def test_register_builtins_adds_calculator() -> None:
    registry = ToolRegistry()
    register_builtins(registry)
    tool = registry.get("calculator")
    assert tool is not None
    assert tool.name == "calculator"
