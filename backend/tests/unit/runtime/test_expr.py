"""Unit tests for the safe condition/loop expression evaluator."""

from __future__ import annotations

import pytest

from app.runtime.expr import ExprEvaluationError, build_namespace, evaluate_condition


def test_simple_comparison_true() -> None:
    ns = build_namespace(output=None, last_tool_result_raw="5", step_index=0)
    assert evaluate_condition("last_tool_result > 3", ns) is True


def test_simple_comparison_false() -> None:
    ns = build_namespace(output=None, last_tool_result_raw="5", step_index=0)
    assert evaluate_condition("last_tool_result > 30", ns) is False


def test_dict_key_dot_access() -> None:
    ns = build_namespace(output=None, last_tool_result_raw='{"score": 0.9}', step_index=0)
    assert evaluate_condition("last_tool_result.score > 0.5", ns) is True


def test_dict_key_bracket_access() -> None:
    ns = build_namespace(output=None, last_tool_result_raw='{"score": 0.2}', step_index=0)
    assert evaluate_condition('last_tool_result["score"] > 0.5', ns) is False


def test_nested_dict_key_access() -> None:
    ns = build_namespace(output=None, last_tool_result_raw='{"scores": {"avg": 0.8}}', step_index=0)
    assert evaluate_condition("last_tool_result.scores.avg > 0.5", ns) is True


def test_missing_key_is_none_not_error() -> None:
    ns = build_namespace(output=None, last_tool_result_raw='{"score": 0.9}', step_index=0)
    assert evaluate_condition("last_tool_result.missing == None", ns) is True


def test_bool_ops_and_not() -> None:
    ns = build_namespace(output="done", last_tool_result_raw="1", step_index=2)
    assert evaluate_condition("step_index == 2 and not (last_tool_result > 5)", ns) is True


def test_string_in_output() -> None:
    ns = build_namespace(output="an error occurred", last_tool_result_raw=None, step_index=0)
    assert evaluate_condition("'error' in output", ns) is True


def test_unknown_name_raises() -> None:
    ns = build_namespace(output=None, last_tool_result_raw=None, step_index=0)
    with pytest.raises(ExprEvaluationError, match="Unknown name"):
        evaluate_condition("bogus_var > 1", ns)


def test_call_rejected() -> None:
    ns = build_namespace(output=None, last_tool_result_raw=None, step_index=0)
    with pytest.raises(ExprEvaluationError):
        evaluate_condition("__import__('os').system('echo hi')", ns)


def test_attribute_access_on_non_dict_rejected() -> None:
    ns = build_namespace(output="plain string", last_tool_result_raw=None, step_index=0)
    with pytest.raises(ExprEvaluationError, match="not a dict"):
        evaluate_condition("output.upper", ns)


def test_invalid_syntax_raises() -> None:
    ns = build_namespace(output=None, last_tool_result_raw=None, step_index=0)
    with pytest.raises(ExprEvaluationError, match="syntax"):
        evaluate_condition("last_tool_result >", ns)
