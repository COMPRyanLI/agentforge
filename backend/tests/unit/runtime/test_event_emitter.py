"""Unit tests for EventEmitter (no DB required)."""

from __future__ import annotations


def test_emit_does_not_call_datetime_now_internally() -> None:
    """EventEmitter.emit must not generate timestamps internally."""
    import inspect

    from app.runtime import event_emitter as ee_module

    source = inspect.getsource(ee_module.EventEmitter.emit)
    assert "datetime.now" not in source, "EventEmitter.emit must not call datetime.now()"
    assert "datetime.utcnow" not in source, "EventEmitter.emit must not call datetime.utcnow()"
