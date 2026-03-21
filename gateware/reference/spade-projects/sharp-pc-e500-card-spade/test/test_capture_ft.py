from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
FIXTURE_PATH = PROJECT_ROOT / "testdata" / "ft_golden.ft16"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from capture_ft import FT_RECORD_BYTES, PyFtdiReader, capture_stream, capture_to_vcd  # noqa: E402


class FakeByteReader:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)
        self.closed = False

    def read(self, size: int) -> bytes:
        return self._chunks.pop(0) if self._chunks else b""

    def close(self) -> None:
        self.closed = True

class FtCaptureTests(unittest.TestCase):
    def test_pyftdi_reader_opens_reads_and_closes(self) -> None:
        events: list[tuple[str, object]] = []

        class FakeFtdi:
            def open_from_url(self, *, url: str) -> None:
                events.append(("open", url))

            def purge_buffers(self) -> None:
                events.append(("purge", None))

            def read_data(self, size: int) -> bytes:
                events.append(("read", size))
                return b"\x34\x12"

            def close(self) -> None:
                events.append(("close", None))

        fake_pkg = types.ModuleType("pyftdi")
        fake_mod = types.ModuleType("pyftdi.ftdi")
        fake_mod.Ftdi = FakeFtdi
        prev_pkg = sys.modules.get("pyftdi")
        prev_mod = sys.modules.get("pyftdi.ftdi")
        sys.modules["pyftdi"] = fake_pkg
        sys.modules["pyftdi.ftdi"] = fake_mod
        try:
            reader = PyFtdiReader("ftdi://ftdi:2232h/2")
            self.assertEqual(reader.read(16), b"\x34\x12")
            reader.close()
        finally:
            if prev_pkg is None:
                sys.modules.pop("pyftdi", None)
            else:
                sys.modules["pyftdi"] = prev_pkg
            if prev_mod is None:
                sys.modules.pop("pyftdi.ftdi", None)
            else:
                sys.modules["pyftdi.ftdi"] = prev_mod

        self.assertEqual(
            events,
            [
                ("open", "ftdi://ftdi:2232h/2"),
                ("purge", None),
                ("read", 16),
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
