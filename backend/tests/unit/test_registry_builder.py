"""Unit tests for the publish-time tool-ownership gate."""

from app.runtime.registry_builder import graph_references_db_backed_tool


def test_builtin_only_graph_is_safe() -> None:
    graph = {
        "nodes": [
            {"id": "in", "type": "input"},
            {"id": "llm1", "type": "llm", "data": {"tools": ["calculator"]}},
            {"id": "out", "type": "output"},
        ],
        "edges": [],
    }
    assert graph_references_db_backed_tool(graph) is False


def test_llm_node_with_non_builtin_tool_name_is_unsafe() -> None:
    graph = {
        "nodes": [
            {"id": "llm1", "type": "llm", "data": {"tools": ["my_http_tool"]}},
        ],
        "edges": [],
    }
    assert graph_references_db_backed_tool(graph) is True


def test_tool_node_with_uuid_tool_id_is_unsafe() -> None:
    graph = {
        "nodes": [
            {
                "id": "t1",
                "type": "tool",
                "data": {"tool_id": "11111111-1111-1111-1111-111111111111"},
            },
        ],
        "edges": [],
    }
    assert graph_references_db_backed_tool(graph) is True


def test_tool_node_with_builtin_name_as_tool_id_is_safe() -> None:
    graph = {
        "nodes": [
            {"id": "t1", "type": "tool", "data": {"tool_id": "calculator"}},
        ],
        "edges": [],
    }
    assert graph_references_db_backed_tool(graph) is False
