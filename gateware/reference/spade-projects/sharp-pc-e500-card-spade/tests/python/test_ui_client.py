from __future__ import annotations

from pathlib import Path

from pce500_host import ui_client
from pce500_host.ui_client import read_ui_state, ui_state_fresh_enough


def test_ui_state_fresh_enough_accepts_initial_state():
    assert ui_state_fresh_enough({"status": "ok"}, None) is True


def test_ui_state_fresh_enough_rejects_non_ok_status():
    assert ui_state_fresh_enough({"status": "error"}, None) is False


def test_ui_state_fresh_enough_accepts_render_generation_advance():
    current = {"status": "ok", "render_generation": 12, "lcd_writes": 4}
    baseline = {"status": "ok", "render_generation": 10, "lcd_writes": 4}
    assert ui_state_fresh_enough(current, baseline) is True


def test_ui_state_fresh_enough_accepts_write_advance():
    current = {"status": "ok", "total_words": 10, "lcd_writes": 5}
    baseline = {"status": "ok", "total_words": 10, "lcd_writes": 4}
    assert ui_state_fresh_enough(current, baseline) is True


def test_ui_state_fresh_enough_rejects_stale_state():
    current = {"status": "ok", "render_generation": 10, "lcd_writes": 4}
    baseline = {"status": "ok", "render_generation": 10, "lcd_writes": 4}
    assert ui_state_fresh_enough(current, baseline) is False


def test_read_ui_state_swallows_runtime_error(monkeypatch):
    monkeypatch.setattr(Path, "exists", lambda self: True)
    monkeypatch.setattr(ui_client, "send_request", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("bad reply")))
    assert read_ui_state(Path("/tmp/pc-e500-live-display.sock")) is None
