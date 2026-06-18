"""Shared fixtures for runtime unit tests.

invoke_tool_idempotent needs a working ToolCallRepo + session_factory, but
unit tests shouldn't need a real Postgres. fake_tool_call_repo monkeypatches
the module-level repo singleton with an in-memory stand-in.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

import app.runtime.registry as registry_module


class FakeToolCall:
    def __init__(
        self, run_id: uuid.UUID, node_id: str, idempotency_key: str, args_json: dict[str, Any]
    ) -> None:
        self.run_id = run_id
        self.node_id = node_id
        self.idempotency_key = idempotency_key
        self.args_json = args_json
        self.status = "pending"
        self.result_json: dict[str, Any] | None = None


class FakeToolCallRepo:
    """In-memory stand-in for ToolCallRepo — no real DB needed for these tests."""

    def __init__(self) -> None:
        self.rows: dict[str, FakeToolCall] = {}

    async def get_by_key(self, session: Any, idempotency_key: str) -> FakeToolCall | None:
        return self.rows.get(idempotency_key)

    async def create_pending(
        self,
        session: Any,
        run_id: uuid.UUID,
        node_id: str,
        idempotency_key: str,
        args_json: dict[str, Any],
    ) -> FakeToolCall:
        row = FakeToolCall(run_id, node_id, idempotency_key, args_json)
        self.rows[idempotency_key] = row
        return row

    async def mark_pending(self, session: Any, tool_call: FakeToolCall) -> FakeToolCall:
        tool_call.status = "pending"
        return tool_call

    async def mark_completed(
        self, session: Any, tool_call: FakeToolCall, result_json: dict[str, Any]
    ) -> FakeToolCall:
        tool_call.status = "completed"
        tool_call.result_json = result_json
        return tool_call

    async def mark_failed(
        self, session: Any, tool_call: FakeToolCall, error_json: dict[str, Any]
    ) -> FakeToolCall:
        tool_call.status = "failed"
        tool_call.result_json = error_json
        return tool_call


class _DummySession:
    """Stands in for AsyncSession — FakeToolCallRepo never touches it, but
    invoke_tool_idempotent itself calls session.commit() directly."""

    async def commit(self) -> None:
        return None


class _DummySessionCtx:
    async def __aenter__(self) -> _DummySession:
        return _DummySession()

    async def __aexit__(self, *_: object) -> None:
        return None


def dummy_session_factory() -> _DummySessionCtx:
    return _DummySessionCtx()


@pytest.fixture
def fake_tool_call_repo(monkeypatch: pytest.MonkeyPatch) -> FakeToolCallRepo:
    fake = FakeToolCallRepo()
    monkeypatch.setattr(registry_module, "_tool_call_repo", fake)
    return fake
