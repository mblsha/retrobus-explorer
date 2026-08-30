#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


CASES: dict[str, tuple[str, str]] = {
    "sync_delay": ("tb_sync_delay", "test_sync_delay"),
    "reset_conditioner": ("tb_reset_conditioner", "test_reset_conditioner"),
    "rising_edge": ("tb_rising_edge", "test_rising_edge"),
    "falling_edge": ("tb_falling_edge", "test_falling_edge"),
    "sync2": ("tb_sync2", "test_sync2"),
    "uart_tx": ("tb_uart_tx", "test_uart_tx"),
    "uart_rx": ("tb_uart_rx", "test_uart_rx"),
    "uart_rx_u16": ("tb_uart_rx_u16", "test_uart_rx_u16"),
    "ft": ("tb_ft", "test_ft_u16"),
    "fifo": ("tb_fifo", "test_fifo"),
    "async_fifo_u8": ("tb_async_fifo_u8", "test_async_fifo_u8"),
    "counter_u8": ("tb_counter_u8", "test_counter_u8"),
    "count_on_event_u8": ("tb_count_on_event_u8", "test_count_on_event_u8"),
    "wait_hold": ("tb_wait_hold", "test_wait_hold"),
    "stream_counter": ("tb_stream_counter", "test_stream_counter"),
    "rom_gate": ("tb_rom_gate", "test_rom_gate"),
    "ascii_message_helpers": ("tb_ascii_message_helpers", "test_ascii_message_helpers"),
    "elastic_slot_u8": ("tb_elastic_buffer_u8", "test_elastic_slot_u8"),
    "message_stream": ("tb_message_stream", "test_message_stream"),
    "async_uart_monitor_queue_only": (
        "tb_async_uart_monitor_queue_only",
        "test_async_uart_monitor_queue_only",
    ),
    "uart_tx_adapter_equiv": ("tb_uart_tx_adapter_equiv", "test_uart_tx_adapter_equiv"),
    "uart_tx_tap_equiv": ("tb_uart_tx_tap_equiv", "test_uart_tx_tap_equiv"),
    "ft_out_tap": ("tb_ft_out_tap", "test_ft_out_tap"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one shared-component cocotb test with VCD output")
    parser.add_argument("component", choices=sorted(CASES.keys()))
    parser.add_argument("extra", nargs=argparse.REMAINDER, help="Extra args forwarded to run_tb.py")
    return parser.parse_args()


def stash_outputs(project: Path, component: str) -> None:
    test_dir = project / "test"
    wave_dir = test_dir / "waveforms"
    wave_dir.mkdir(parents=True, exist_ok=True)

    artifacts = [
        ("dump.vcd", f"{component}.vcd"),
        ("dump.surfer.vcd", f"{component}.surfer.vcd"),
        ("results.xml", f"{component}.results.xml"),
    ]
    for src_name, dst_name in artifacts:
        src = test_dir / src_name
        if src.exists():
            shutil.copyfile(src, wave_dir / dst_name)


def main() -> int:
    args = parse_args()
    component = args.component
    top, test_module = CASES[component]

    project = Path(__file__).resolve().parent.parent
    tool = project.parents[1] / "tools" / "project.py"
    build_dir = f"build/{top}_cocotb"

    cmd = [
        sys.executable,
        str(tool),
        "test-with-vcd",
        "--project",
        str(project),
        "--top",
        top,
        "--test-module",
        test_module,
        "--build-dir",
        build_dir,
        *args.extra,
    ]
    subprocess.run(cmd, check=True)
    stash_outputs(project, component)
    print(f"component: {component}")
    print(f"top: {top}")
    print(f"test module: {test_module}")
    print(f"build dir: {project / build_dir}")
    print(f"waveforms: {project / 'test' / 'waveforms'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
