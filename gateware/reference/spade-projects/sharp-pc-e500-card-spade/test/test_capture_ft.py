from __future__ import annotations

import sys
import tempfile
import types
import unittest
import ctypes
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
FIXTURE_PATH = PROJECT_ROOT / "testdata" / "ft_golden.ft16"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from capture_ft import D3xxReader, FT_RECORD_BYTES, capture_stream, capture_to_vcd  # noqa: E402


class FakeByteReader:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)
        self.closed = False

    def read(self, size: int) -> bytes:
        return self._chunks.pop(0) if self._chunks else b""

    def close(self) -> None:
        self.closed = True

class FtCaptureTests(unittest.TestCase):
    def test_d3xx_reader_opens_reads_and_closes(self) -> None:
        events: list[tuple[str, object]] = []

        class FakeDevice:
            handle = 99
            def close(self) -> None:
                events.append(("close", None))

        def fake_create(index: int, flag: int):
            events.append(("open", (index, flag)))
            return FakeDevice()

        def fake_call_ft(func, handle, channel, data, datalen, bytes_transferred, timeout_ms):
            events.append(("read", (func, handle, int(channel.value), int(datalen.value), timeout_ms)))
            payload = b"\x34\x12"
            ctypes.memmove(data, payload, len(payload))
            bytes_transferred._obj.value = len(payload)

        fake_mft = types.ModuleType("_ftd3xx_linux")
        fake_mft.FT_OPEN_BY_INDEX = 7
        fake_mft.FT_ReadPipeEx = object()
        fake_mft.ULONG = ctypes.c_ulong
        fake_mft.UCHAR = ctypes.c_ubyte
        fake_ftd3xx = types.ModuleType("ftd3xx")
        fake_ftd3xx.create = fake_create
        fake_ftd3xx.call_ft = fake_call_ft
        prev_mft = sys.modules.get("_ftd3xx_linux")
        prev_ftd3xx = sys.modules.get("ftd3xx")
        sys.modules["_ftd3xx_linux"] = fake_mft
        sys.modules["ftd3xx"] = fake_ftd3xx
        try:
            reader = D3xxReader(device_index=2, channel=1, timeout_ms=250)
            self.assertEqual(reader.read(16), b"\x34\x12")
            reader.close()
        finally:
            if prev_mft is None:
                sys.modules.pop("_ftd3xx_linux", None)
            else:
                sys.modules["_ftd3xx_linux"] = prev_mft
            if prev_ftd3xx is None:
                sys.modules.pop("ftd3xx", None)
            else:
                sys.modules["ftd3xx"] = prev_ftd3xx

        self.assertEqual(
            events,
            [
                ("open", (2, 7)),
                ("read", (fake_mft.FT_ReadPipeEx, 99, 1, 16, 250)),
                ("close", None),
            ],
        )

    def test_capture_stream_trims_partial_record_tail(self) -> None:
        fixture = FIXTURE_PATH.read_bytes()
        chunks = [fixture + b"\xAA\xBB\xCC"]
        reader = FakeByteReader(chunks)

        with tempfile.TemporaryDirectory() as tmpdir:
            raw_out = Path(tmpdir) / "capture.ft16"
            stats = capture_stream(
                reader,
                raw_out,
                duration_s=None,
                idle_timeout_s=0.0,
                poll_interval_s=0.0,
                sleep=lambda _seconds: None,
            )

            self.assertEqual(stats.raw_bytes, len(fixture) + 3)
            self.assertEqual(stats.aligned_bytes, len(fixture))
            self.assertEqual(stats.trimmed_bytes, 3)
            self.assertEqual(raw_out.read_bytes(), fixture)

    def test_capture_stream_preserves_complete_records(self) -> None:
        payload = FIXTURE_PATH.read_bytes()
        reader = FakeByteReader([payload[:7], payload[7:]])

        with tempfile.TemporaryDirectory() as tmpdir:
            raw_out = Path(tmpdir) / "capture.ft16"
            stats = capture_stream(
                reader,
                raw_out,
                duration_s=None,
                idle_timeout_s=0.0,
                poll_interval_s=0.0,
                sleep=lambda _seconds: None,
            )

            self.assertEqual(stats.raw_bytes, len(payload))
            self.assertEqual(stats.trimmed_bytes, 0)
            self.assertEqual(raw_out.read_bytes(), payload)

    def test_capture_to_vcd_writes_both_outputs(self) -> None:
        reader = FakeByteReader([FIXTURE_PATH.read_bytes()])

        with tempfile.TemporaryDirectory() as tmpdir:
            raw_out = Path(tmpdir) / "capture.ft16"
            vcd_out = Path(tmpdir) / "trace.vcd"
            stats = capture_to_vcd(
                reader,
                raw_out=raw_out,
                vcd_out=vcd_out,
                duration_s=None,
                idle_timeout_s=0.0,
                poll_interval_s=0.0,
            )

            self.assertEqual(stats.trimmed_bytes, 0)
            self.assertTrue(raw_out.exists())
            self.assertTrue(vcd_out.exists())

            vcd = vcd_out.read_text()
            self.assertIn("event_sync", vcd)
            self.assertIn("event_config", vcd)
            self.assertIn("event_ce1_read", vcd)
            self.assertIn("event_bus_change", vcd)
            self.assertIn("#70630", vcd)
            self.assertIn("b01011010", vcd)


if __name__ == "__main__":
    unittest.main()
