from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
FIXTURE_PATH = PROJECT_ROOT / "testdata" / "ft_golden.ft16"
CE6_FIXTURE_PATH = PROJECT_ROOT / "testdata" / "ft_golden_ce6.ft16"
OVERFLOW_FIXTURE_PATH = PROJECT_ROOT / "testdata" / "ft_golden_overflow_record.ft16"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from e500_ft import (  # noqa: E402
    FT_STREAM_VERSION,
    FT_DATA_SHIFT,
    decode_ft_record,
    FtKind,
    FtStreamVersionError,
    config_delay_ticks,
    config_enabled,
    iter_ft_records_from_bytes,
    iter_timed_records,
    overflow_count,
    ft_record_from_words,
    iter_ft_words_from_bytes,
    read_ft_records,
    sync_version,
)
from ft_to_vcd import build_vcd  # noqa: E402


def load_fixture_records():
    return read_ft_records(FIXTURE_PATH)


def load_ce6_fixture_records():
    return read_ft_records(CE6_FIXTURE_PATH)


def load_overflow_fixture_record():
    words = list(iter_ft_words_from_bytes(OVERFLOW_FIXTURE_PATH.read_bytes()))
    return ft_record_from_words(words)


def mutate_first_record_version(raw: bytes, version: int) -> bytes:
    record = int.from_bytes(raw[:10], "little")
    record &= ~(0xFF << FT_DATA_SHIFT)
    record |= (version & 0xFF) << FT_DATA_SHIFT
    return record.to_bytes(10, "little") + raw[10:]


class FtDecodeTests(unittest.TestCase):
    def test_decode_sync_record(self) -> None:
        record = load_fixture_records()[0]
        self.assertEqual(record.kind, FtKind.SYNC)
        self.assertEqual(record.delta_ticks, 0)
        self.assertEqual(sync_version(record), FT_STREAM_VERSION)

    def test_decode_config_record(self) -> None:
        record = load_fixture_records()[1]
        self.assertEqual(record.kind, FtKind.CONFIG)
        self.assertEqual(record.delta_ticks, 1)
        self.assertEqual(config_delay_ticks(record), 50)
        self.assertTrue(config_enabled(record))

    def test_decode_access_record_aux_flags(self) -> None:
        write, read0, read1 = load_fixture_records()[2:5]
        self.assertEqual(write.kind, FtKind.CE1_WRITE)
        self.assertEqual(write.addr, 0x0123)
        self.assertEqual(write.data, 0x5A)
        self.assertFalse(write.aux.rw)
        self.assertTrue(write.aux.oe)
        self.assertTrue(write.aux.ce1)
        self.assertFalse(write.aux.same_addr)
        self.assertFalse(write.aux.same_data)
        self.assertTrue(write.aux.classified_after_delay)

        for record in (read0, read1):
            self.assertEqual(record.kind, FtKind.CE1_READ)
            self.assertEqual(record.addr, 0x0123)
            self.assertEqual(record.data, 0x5A)
            self.assertTrue(record.aux.rw)
            self.assertFalse(record.aux.oe)
            self.assertTrue(record.aux.ce1)
            self.assertFalse(record.aux.ce6)
            self.assertTrue(record.aux.same_addr)
            self.assertTrue(record.aux.same_data)
            self.assertTrue(record.aux.classified_after_delay)
        self.assertEqual(write.delta_ticks, 7010)
        self.assertEqual(read0.delta_ticks, 74)
        self.assertEqual(read1.delta_ticks, 74)

    def test_decode_overflow_record(self) -> None:
        record = load_overflow_fixture_record()
        self.assertEqual(record.kind, FtKind.OVERFLOW)
        self.assertEqual(overflow_count(record), 298)

    def test_decode_ce6_records_aux_flags(self) -> None:
        ce6_read, ce6_write_attempt = load_ce6_fixture_records()[2:4]

        self.assertEqual(ce6_read.kind, FtKind.CE6_READ)
        self.assertEqual(ce6_read.addr, 0x0021)
        self.assertEqual(ce6_read.data, 0xA7)
        self.assertTrue(ce6_read.aux.rw)
        self.assertFalse(ce6_read.aux.oe)
        self.assertFalse(ce6_read.aux.ce1)
        self.assertTrue(ce6_read.aux.ce6)

        self.assertEqual(ce6_write_attempt.kind, FtKind.CE6_WRITE_ATTEMPT)
        self.assertEqual(ce6_write_attempt.addr, 0x0021)
        self.assertEqual(ce6_write_attempt.data, 0x3C)
        self.assertFalse(ce6_write_attempt.aux.rw)
        self.assertTrue(ce6_write_attempt.aux.oe)
        self.assertFalse(ce6_write_attempt.aux.ce1)
        self.assertTrue(ce6_write_attempt.aux.ce6)

    def test_reassemble_fixture_from_bytes(self) -> None:
        records = list(iter_ft_records_from_bytes(FIXTURE_PATH.read_bytes()))
        self.assertEqual(len(records), 5)
        self.assertEqual(records[2].kind, FtKind.CE1_WRITE)
        self.assertEqual(records[3].kind, FtKind.CE1_READ)

    def test_timed_records_accumulate_delta(self) -> None:
        timed = list(iter_timed_records(load_fixture_records()))
        self.assertEqual([item.tick for item in timed], [0, 1, 7011, 7085, 7159])

    def test_invalid_stream_version_is_rejected(self) -> None:
        bad = mutate_first_record_version(FIXTURE_PATH.read_bytes(), FT_STREAM_VERSION + 1)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bad.ft16"
            path.write_bytes(bad)
            with self.assertRaises(FtStreamVersionError):
                read_ft_records(path)
        with self.assertRaises(FtStreamVersionError):
            build_vcd(list(iter_ft_records_from_bytes(bad)))


class FtVcdTests(unittest.TestCase):
    def test_build_vcd_for_access_and_meta_records(self) -> None:
        records = load_fixture_records() + load_ce6_fixture_records()[2:4] + [load_overflow_fixture_record()]
        vcd = build_vcd(records)

        self.assertIn("$var wire 18", vcd)
        self.assertIn("bus_addr", vcd)
        self.assertIn("event_ce1_read", vcd)
        self.assertIn("event_overflow", vcd)
        self.assertIn("event_ce6_read", vcd)
        self.assertIn("event_ce6_write_attempt", vcd)

        # Time points are in ns with 10 ns per tick.
        self.assertIn("#10", vcd)      # config at 1 tick
        self.assertIn("#70110", vcd)   # write at 7011 ticks
        self.assertIn("#70850", vcd)   # first read at 7085 ticks
        self.assertIn("#71590", vcd)   # second read at 7159 ticks

        # Access values get pushed into bus vectors.
        self.assertIn("b000000000100100011", vcd)  # addr 0x123 on 18-bit bus
        self.assertIn("b01011010", vcd)          # data 0x5A
        self.assertIn("b000000000000100001", vcd)  # addr 0x021 on 18-bit bus
        self.assertIn("b10100111", vcd)            # data 0xA7
        self.assertIn("b00111100", vcd)            # data 0x3C

        # Meta/config values are represented too.
        self.assertIn("b000000000000110010", vcd)  # classify delay 50 ticks
        self.assertIn(f"b{298:026b}", vcd)


if __name__ == "__main__":
    unittest.main()
