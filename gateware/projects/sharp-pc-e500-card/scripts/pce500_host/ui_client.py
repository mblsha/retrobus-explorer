from __future__ import annotations

import time
from pathlib import Path

from .supervisor_client import send_request


DEFAULT_UI_SOCKET = Path("/tmp/pc-e500-live-display.sock")


def read_ui_state(socket_path: Path) -> dict[str, object] | None:
    if not socket_path.exists():
        return None
    try:
        return send_request(socket_path, {"action": "get_text"})
    except (OSError, RuntimeError, ValueError):
        return None


def ui_state_fresh_enough(
    current: dict[str, object],
    baseline: dict[str, object] | None,
) -> bool:
    if current.get("status") != "ok":
        return False
    if baseline is None:
        return True
    current_generation = current.get("render_generation")
    baseline_generation = baseline.get("render_generation")
    current_writes = current.get("lcd_writes")
    baseline_writes = baseline.get("lcd_writes")
    if (
        isinstance(current_generation, int)
        and isinstance(baseline_generation, int)
        and current_generation > baseline_generation
    ):
        return True
    if isinstance(current_writes, int) and isinstance(baseline_writes, int) and current_writes > baseline_writes:
        return True
    return False


def try_ui_render(
    socket_path: Path,
    *,
    baseline: dict[str, object] | None,
    retries: int = 5,
    delay_s: float = 0.1,
) -> dict[str, object] | None:
    if not socket_path.exists():
        return None
    last = None
    for _ in range(retries):
        last = read_ui_state(socket_path)
        if last and ui_state_fresh_enough(last, baseline):
            lines = last.get("lines")
            if isinstance(lines, list) and any(isinstance(line, str) and line for line in lines):
                return last
        time.sleep(delay_s)
    if last and ui_state_fresh_enough(last, baseline):
        return last
    return None
