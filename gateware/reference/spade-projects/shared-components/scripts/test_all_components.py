#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


COMPONENTS = [
    "sync_delay",
    "reset_conditioner",
    "rising_edge",
    "falling_edge",
    "sync2",
    "my_uart_tx",
    "uart_rx",
    "ft",
    "fifo_u8",
    "async_fifo_u8",
    "counter_u8",
    "count_on_event_u8",
    "wait_hold",
    "stream_counter",
    "rom_gate",
]


def main() -> int:
    script = Path(__file__).resolve().parent / "test_component.py"
    for component in COMPONENTS:
        print(f"== Running {component} ==")
        subprocess.run([sys.executable, str(script), component, *sys.argv[1:]], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
