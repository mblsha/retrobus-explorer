#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyserial>=3.5"]
# ///
from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from pc_e500_experiment_common import (
    BEGIN_PREFIX,
    DEFAULT_ASSEMBLER_DIR,
    DEFAULT_BAUD,
    DEFAULT_FILL_BYTE,
    DEFAULT_IDLE_GAP,
    DEFAULT_QUIET_TIMEOUT,
    END_PREFIX,
    READY_PREFIX,
    assemble_segments,
    assemble_text,
    build_card_rom_image,
    open_uart,
    render_terminal_bytes,
    resolve_existing_dir,
    resolve_existing_file,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOCKET = Path.home() / ".cache" / "pc-e500-expd.sock"
DEFAULT_SAFE_ASM = PROJECT_ROOT / "asm" / "card_rom_supervisor_safe.asm"
DEFAULT_DEBUG_ECHO_ASM = PROJECT_ROOT / "asm" / "card_rom_echo_short_retf.asm"

CMD_BASE = 0x107E0
CMD_MAGIC0 = CMD_BASE + 0x00
CMD_MAGIC1 = CMD_BASE + 0x01
CMD_VERSION = CMD_BASE + 0x02
CMD_FLAGS = CMD_BASE + 0x03
CMD_START_TAG = CMD_BASE + 0x04
CMD_STOP_TAG = CMD_BASE + 0x05
CMD_ARGS_BASE = CMD_BASE + 0x06
CMD_ARGS_COUNT = 10
CMD_SEQ = 0x107FF

EXPERIMENT_MIN = 0x10100
EXPERIMENT_MAX = 0x106FF


def json_dumps(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PC-E500 experiment supervisor daemon")
    parser.add_argument("--socket", type=Path, default=DEFAULT_SOCKET, help=f"unix socket path (default: {DEFAULT_SOCKET})")
    parser.add_argument("--port", help="USB-UART port; defaults to the second /dev/cu.usbserial-* device")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD, help=f"UART baud rate (default: {DEFAULT_BAUD})")
    parser.add_argument("--idle-gap", type=float, default=DEFAULT_IDLE_GAP, help=f"quiet gap before host writes (default: {DEFAULT_IDLE_GAP})")
    parser.add_argument(
        "--quiet-timeout",
        type=float,
        default=DEFAULT_QUIET_TIMEOUT,
        help=f"max wait for UART quiet before a host command (default: {DEFAULT_QUIET_TIMEOUT})",
    )
    parser.add_argument("--assembler-dir", type=Path, default=DEFAULT_ASSEMBLER_DIR, help="SC62015 assembler checkout")
    parser.add_argument("--safe-asm", type=Path, default=DEFAULT_SAFE_ASM, help="safe supervisor assembly image")
    parser.add_argument(
        "--arm-safe-on-start",
        action="store_true",
        help="program the safe supervisor image immediately at daemon startup",
    )
    parser.add_argument(
        "--monitor-uart",
        action="store_true",
        help="mirror background UART traffic to stdout",
    )
    return parser


class ExperimentDaemon:
    def __init__(
        self,
        *,
        port: str | None,
        baud: int,
        idle_gap: float,
        quiet_timeout: float,
        assembler_dir: Path,
        safe_asm: Path,
        monitor_uart: bool,
    ) -> None:
        self.assembler_dir = resolve_existing_dir(assembler_dir, "assembler checkout")
        self.safe_asm = resolve_existing_file(safe_asm, "safe supervisor assembly")
        self.ser, self.uart = open_uart(
            port,
            baud=baud,
            idle_gap=idle_gap,
            quiet_timeout=quiet_timeout,
            monitor_stream=sys.stdout if monitor_uart else None,
        )
        self.status = "waiting_for_call"
        self.needs_reset = False
        self.last_error: str | None = None
        self.last_result: dict[str, Any] | None = None
        self.last_ready_line: str | None = None
        self.safe_image_programmed = False
        self.safe_image_path: str | None = None
        self.safe_image_entry: int | None = None
        self.debug_echo_asm = resolve_existing_file(DEFAULT_DEBUG_ECHO_ASM, "debug echo assembly")
        self._next_seq = 1
        self._scan_index = 0
        self._run_counter = 0

    def close(self) -> None:
        self.uart.close()
        self.ser.close()

    def _make_run_id(self) -> str:
        self._run_counter += 1
        return f"{time.strftime('%Y%m%d-%H%M%S')}-{self._run_counter:04d}"

    def _poll_unsolicited_lines(self) -> None:
        lines = self.uart.lines_since(self._scan_index)
        self._scan_index += len(lines)
        for line in lines:
            if line.text.startswith(READY_PREFIX):
                self.status = "idle"
                self.needs_reset = False
                self.last_error = None
                self.last_ready_line = line.text

    def _next_sequence(self) -> int:
        value = self._next_seq & 0xFF
        if value == 0:
            value = 1
        self._next_seq = value + 1
        return value

    def _assemble_image_from_source(self, source_path: Path) -> tuple[int, bytes]:
        segments = assemble_segments(resolve_existing_file(source_path, "assembly source"), self.assembler_dir)
        return build_card_rom_image(segments, DEFAULT_FILL_BYTE)

    def _assemble_image_from_text(self, source_text: str) -> tuple[int, bytes]:
        segments = assemble_text(source_text, self.assembler_dir)
        return build_card_rom_image(segments, DEFAULT_FILL_BYTE)

    def program_safe_image(self) -> dict[str, Any]:
        start_address, image = self._assemble_image_from_source(self.safe_asm)
        self.uart.write_rom_bytes(start_address, image, fast=True)
        self.safe_image_programmed = True
        self.safe_image_path = str(self.safe_asm)
        self.safe_image_entry = start_address
        self.status = "waiting_for_call"
        self.needs_reset = False
        self.last_error = None
        return {
            "status": "ok",
            "safe_image_programmed": True,
            "safe_image_path": str(self.safe_asm),
            "entry": start_address,
        }

    def debug_echo_short(self, timeout_s: float) -> dict[str, Any]:
        start_address, image = self._assemble_image_from_source(self.debug_echo_asm)

        self.uart.set_timing(5)
        self.uart.set_control_timing(10)
        self.uart.write_rom_bytes(start_address, image, fast=True)
        self.uart.synchronize_rx_boundary()
        raw_index = self.uart.raw_count()

        try:
            captured = self.uart.wait_for_bytes(b"OK\r\n", timeout_s, start_index=raw_index)
        except TimeoutError as exc:
            recent = self.uart.raw_since(raw_index)
            payload = {
                "status": "timeout",
                "action": "debug_echo_short",
                "entry": start_address,
                "asm_path": str(self.debug_echo_asm),
                "needs_reset": False,
                "error": str(exc),
                "captured_text": render_terminal_bytes(recent),
                "captured_hex": recent.hex(),
                "message": "Run CALL &10100 on the PC-E500 while this command is waiting.",
            }
            self.last_result = payload
            return payload

        payload = {
            "status": "ok",
            "action": "debug_echo_short",
            "entry": start_address,
            "asm_path": str(self.debug_echo_asm),
            "captured_text": render_terminal_bytes(captured),
            "captured_hex": captured.hex(),
            "message": "Observed OK\\r\\n from the debug echo payload.",
        }
        self.last_result = payload
        return payload

    def _load_plan(self, script_path: Path, script_args: list[str]) -> dict[str, Any]:
        script_path = resolve_existing_file(script_path, "experiment script")
        completed = subprocess.run(
            [sys.executable, str(script_path), "plan", *script_args],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"experiment plan failed for {script_path}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
            )
        payload = json.loads(completed.stdout)
        payload["_script_path"] = str(script_path)
        payload["_script_args"] = list(script_args)
        return payload

    def _parse_experiment_result(
        self,
        script_path: Path,
        script_args: list[str],
        raw_result: dict[str, Any],
    ) -> dict[str, Any] | None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(raw_result, handle)
            temp_path = Path(handle.name)
        try:
            completed = subprocess.run(
                [sys.executable, str(script_path), "parse", str(temp_path), *script_args],
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode != 0:
                return None
            return json.loads(completed.stdout)
        finally:
            try:
                temp_path.unlink()
            except OSError:
                pass

    def _build_full_experiment_region(self, start_address: int, image: bytes) -> bytes:
        if start_address != EXPERIMENT_MIN:
            raise RuntimeError(
                f"experiment entry must start at {EXPERIMENT_MIN:05X}; assembled image starts at {start_address:05X}"
            )
        if start_address < EXPERIMENT_MIN or start_address + len(image) - 1 > EXPERIMENT_MAX:
            raise RuntimeError(
                f"experiment image spans {start_address:05X}..{start_address + len(image) - 1:05X}, "
                f"outside experiment region {EXPERIMENT_MIN:05X}..{EXPERIMENT_MAX:05X}"
            )
        region = bytearray([DEFAULT_FILL_BYTE]) * (EXPERIMENT_MAX - EXPERIMENT_MIN + 1)
        offset = start_address - EXPERIMENT_MIN
        region[offset : offset + len(image)] = image
        return bytes(region)

    def _compose_command_block(self, plan: dict[str, Any], sequence: int) -> bytes:
        block = bytearray([0x00] * (CMD_SEQ - CMD_BASE + 1))
        block[CMD_MAGIC0 - CMD_BASE] = 0x58
        block[CMD_MAGIC1 - CMD_BASE] = 0x52
        block[CMD_VERSION - CMD_BASE] = 0x01
        block[CMD_FLAGS - CMD_BASE] = int(plan.get("flags", 0)) & 0xFF
        block[CMD_START_TAG - CMD_BASE] = int(plan.get("start_tag", 0x11)) & 0xFF
        block[CMD_STOP_TAG - CMD_BASE] = int(plan.get("stop_tag", 0x12)) & 0xFF
        args = plan.get("args", [])
        if len(args) > CMD_ARGS_COUNT:
            raise RuntimeError(f"experiment args exceed {CMD_ARGS_COUNT} bytes")
        for index, value in enumerate(args):
            block[(CMD_ARGS_BASE - CMD_BASE) + index] = int(value) & 0xFF
        block[CMD_SEQ - CMD_BASE] = sequence & 0xFF
        return bytes(block)

    def _commit_command_block(self, block: bytes) -> None:
        body = block[:-1]
        seq = block[-1]
        self.uart.write_rom_bytes(CMD_BASE, body, fast=True)
        self.uart.write_rom_byte(CMD_SEQ, seq)

    def _handle_timeout(self, *, run_id: str, reason: str) -> dict[str, Any]:
        self.status = "needs_reset"
        self.needs_reset = True
        self.last_error = reason
        safe_programmed = False
        safe_error = None
        try:
            result = self.program_safe_image()
            safe_programmed = bool(result["safe_image_programmed"])
        except Exception as exc:  # noqa: BLE001
            safe_error = str(exc)
        self.status = "needs_reset"
        self.needs_reset = True
        self.last_error = reason
        payload = {
            "status": "timeout",
            "run_id": run_id,
            "needs_reset": True,
            "safe_image_programmed": safe_programmed,
            "safe_image_error": safe_error,
            "message": "Reset the PC-E500 and run CALL &10000 again.",
            "error": reason,
        }
        self.last_result = payload
        return payload

    def run_experiment(self, script_path: Path, script_args: list[str]) -> dict[str, Any]:
        self._poll_unsolicited_lines()
        if self.status != "idle" or self.needs_reset:
            raise RuntimeError("device is not idle; wait for XR,READY or reset + CALL &10000")

        plan = self._load_plan(script_path, script_args)
        run_id = self._make_run_id()
        timing = int(plan.get("timing", 5))
        control_timing = int(plan.get("control_timing", 10))
        timeout_s = float(plan.get("timeout_s", 2.0))

        if "asm_source" in plan:
            start_address, image = self._assemble_image_from_source(Path(plan["asm_source"]))
        elif "asm_text" in plan:
            start_address, image = self._assemble_image_from_text(str(plan["asm_text"]))
        else:
            raise RuntimeError("experiment plan must provide asm_source or asm_text")

        full_region = self._build_full_experiment_region(start_address, image)
        sequence = self._next_sequence()
        command_block = self._compose_command_block(plan, sequence)

        self.uart.set_timing(timing)
        self.uart.set_control_timing(control_timing)
        self.uart.clear_measurements()

        line_index = self.uart.line_count()
        self.uart.write_rom_bytes(EXPERIMENT_MIN, full_region, fast=True)
        self._commit_command_block(command_block)
        self.status = "running"

        begin_text = f"{BEGIN_PREFIX},{sequence:02X}"
        end_prefix = f"{END_PREFIX},{sequence:02X},"

        try:
            begin_line = self.uart.wait_for_line(lambda text: text == begin_text, timeout_s, start_index=line_index)
            end_line = self.uart.wait_for_line(lambda text: text.startswith(end_prefix), timeout_s, start_index=line_index)
        except TimeoutError as exc:
            return self._handle_timeout(run_id=run_id, reason=str(exc))

        measurements = self.uart.dump_measurements()
        xr_lines = [line.text for line in self.uart.lines_since(line_index) if line.text.startswith("XR,")]

        result: dict[str, Any] = {
            "status": "ok",
            "run_id": run_id,
            "needs_reset": False,
            "experiment": plan.get("name", Path(script_path).stem),
            "script_path": str(script_path),
            "script_args": list(script_args),
            "timing": timing,
            "control_timing": control_timing,
            "begin_line": begin_line.text,
            "end_line": end_line.text,
            "measurement": [measurement.__dict__ for measurement in measurements],
            "uart_lines": xr_lines,
            "plan": {
                key: value
                for key, value in plan.items()
                if not key.startswith("_")
            },
        }

        parsed = self._parse_experiment_result(Path(plan["_script_path"]), list(plan["_script_args"]), result)
        if parsed is not None:
            result["parsed"] = parsed

        self.status = "idle"
        self.needs_reset = False
        self.last_error = None
        self.last_result = result
        return result

    def status_payload(self) -> dict[str, Any]:
        self._poll_unsolicited_lines()
        return {
            "status": "ok",
            "device_state": self.status,
            "needs_reset": self.needs_reset,
            "last_error": self.last_error,
            "last_ready_line": self.last_ready_line,
            "safe_image_programmed": self.safe_image_programmed,
            "safe_image_path": self.safe_image_path,
            "safe_image_entry": self.safe_image_entry,
            "uart": self.uart.stats(),
            "recent_uart_lines": self.uart.last_lines(),
        }

    def wait_ready(self, timeout_s: float) -> dict[str, Any]:
        self._poll_unsolicited_lines()
        if self.status == "idle":
            return self.status_payload()
        try:
            line = self.uart.wait_for_line(lambda text: text.startswith(READY_PREFIX), timeout_s, start_index=self._scan_index)
        except TimeoutError as exc:
            raise RuntimeError(str(exc)) from exc
        self.last_ready_line = line.text
        self.status = "idle"
        self.needs_reset = False
        return self.status_payload()


def handle_request(daemon: ExperimentDaemon, request: dict[str, Any]) -> dict[str, Any]:
    action = request.get("action")
    if action == "status":
        return daemon.status_payload()
    if action == "arm_safe":
        return daemon.program_safe_image()
    if action == "debug_echo_short":
        timeout_s = float(request.get("timeout_s", 10.0))
        return daemon.debug_echo_short(timeout_s)
    if action == "wait_ready":
        timeout_s = float(request.get("timeout_s", 30.0))
        return daemon.wait_ready(timeout_s)
    if action == "run":
        script_path = Path(str(request["script"]))
        script_args = [str(value) for value in request.get("script_args", [])]
        return daemon.run_experiment(script_path, script_args)
    if action == "shutdown":
        return {"status": "ok", "shutdown": True}
    raise RuntimeError(f"unknown action {action!r}")


def serve(socket_path: Path, daemon: ExperimentDaemon) -> int:
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    if socket_path.exists():
        socket_path.unlink()

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(socket_path))
        server.listen(1)
        try:
            while True:
                conn, _ = server.accept()
                with conn:
                    payload = bytearray()
                    while True:
                        chunk = conn.recv(4096)
                        if not chunk:
                            break
                        payload.extend(chunk)
                        if b"\n" in chunk:
                            break
                    if not payload:
                        continue
                    try:
                        request = json.loads(payload.decode("utf-8"))
                        response = handle_request(daemon, request)
                    except Exception as exc:  # noqa: BLE001
                        response = {
                            "status": "error",
                            "error": str(exc),
                        }
                    conn.sendall(json_dumps(response))
                    if response.get("shutdown"):
                        break
        finally:
            try:
                socket_path.unlink()
            except OSError:
                pass
    return 0


def main() -> int:
    args = build_parser().parse_args()
    daemon = ExperimentDaemon(
        port=args.port,
        baud=args.baud,
        idle_gap=args.idle_gap,
        quiet_timeout=args.quiet_timeout,
        assembler_dir=args.assembler_dir,
        safe_asm=args.safe_asm,
        monitor_uart=args.monitor_uart,
    )
    try:
        if args.arm_safe_on_start:
            daemon.program_safe_image()
        return serve(args.socket, daemon)
    finally:
        daemon.close()


if __name__ == "__main__":
    raise SystemExit(main())
