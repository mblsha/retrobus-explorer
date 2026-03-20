from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from capture_ft import FT_RECORD_BYTES, capture_stream, capture_to_vcd  # noqa: E402
from e500_ft import FT_STREAM_VERSION, FtKind, pack_ft_record, pack_ft_words  # noqa: E402


class FakeByteReader:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)
        self.closed = False

    def read(self, size: int) -> bytes:
        return self._chunks.pop(0) if self._chunks else b""

    def close(self) -> None:
        self.closed = True


def raw_record_bytes(*records: int) -> bytes:
    payload = bytearray()
    for record in records:
        for word in pack_ft_words(record):
            payload.extend(word.to_bytes(2, "little"))
    return bytes(payload)


class FtCaptureTests(unittest.TestCase):
    def test_capture_stream_trims_partial_record_tail(self) -> None:
        sync = pack_ft_record(FtKind.SYNC, 0, 0, FT_STREAM_VERSION, 0)
        chunks = [raw_record_bytes(sync) + b"\xAA\xBB\xCC"]
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

            self.assertEqual(stats.raw_bytes, FT_RECORD_BYTES + 3)
            self.assertEqual(stats.aligned_bytes, FT_RECORD_BYTES)
            self.assertEqual(stats.trimmed_bytes, 3)
            self.assertEqual(raw_out.read_bytes(), raw_record_bytes(sync))

    def test_capture_stream_preserves_complete_records(self) -> None:
        sync = pack_ft_record(FtKind.SYNC, 0, 0, FT_STREAM_VERSION, 0)
        config = pack_ft_record(FtKind.CONFIG, 5, 50, 0, 1)
        payload = raw_record_bytes(sync, config)
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
        sync = pack_ft_record(FtKind.SYNC, 0, 0, FT_STREAM_VERSION, 0)
        config = pack_ft_record(FtKind.CONFIG, 5, 50, 0, 1)
        access = pack_ft_record(FtKind.CE1_READ, 73, 0x0123, 0x5A, 0b1000101)
        reader = FakeByteReader([raw_record_bytes(sync, config, access)])

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
            self.assertIn("#780", vcd)
            self.assertIn("b01011010", vcd)


if __name__ == "__main__":
    unittest.main()
