from __future__ import annotations

from dataclasses import replace
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
    FtKind,
    FtStreamVersionError,
    config_delay_ticks,
    config_enabled,
    ft_record_from_words,
    iter_ft_records_from_bytes,
    iter_ft_words_from_bytes,
    iter_timed_records,
    overflow_count,
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

    def test_decode_raw_bus_change_records(self) -> None:
        write0, write1, read0 = load_fixture_records()[2:5]

        self.assertEqual(write0.kind, FtKind.CE1_WRITE)
        self.assertEqual(write0.addr, 0x0000)
        self.assertEqual(write0.data, 0x00)
        self.assertFalse(write0.aux.rw)
        self.assertTrue(write0.aux.oe)
        self.assertTrue(write0.aux.ce1)
        self.assertTrue(write0.aux.same_addr)
        self.assertTrue(write0.aux.same_data)
        self.assertTrue(write0.aux.change_record)

        self.assertEqual(write1.kind, FtKind.CE1_WRITE)
        self.assertEqual(write1.addr, 0x0123)
        self.assertEqual(write1.data, 0x5A)
        self.assertFalse(write1.aux.rw)
        self.assertTrue(write1.aux.oe)
        self.assertTrue(write1.aux.ce1)
        self.assertFalse(write1.aux.ce6)
        self.assertFalse(write1.aux.same_addr)
        self.assertFalse(write1.aux.same_data)
        self.assertTrue(write1.aux.change_record)

        self.assertEqual(read0.kind, FtKind.CE1_READ)
        self.assertEqual(read0.addr, 0x0123)
        self.assertEqual(read0.data, 0x5A)
        self.assertTrue(read0.aux.rw)
        self.assertTrue(read0.aux.oe)
        self.assertTrue(read0.aux.ce1)
        self.assertFalse(read0.aux.ce6)
        self.assertTrue(read0.aux.same_addr)
        self.assertTrue(read0.aux.same_data)
        self.assertTrue(read0.aux.change_record)

        self.assertEqual(write0.delta_ticks, 7010)
        self.assertEqual(write1.delta_ticks, 8)
        self.assertEqual(read0.delta_ticks, 44)

    def test_decode_overflow_record(self) -> None:
        record = load_overflow_fixture_record()
        self.assertEqual(record.kind, FtKind.OVERFLOW)
        self.assertEqual(overflow_count(record), 298)

    def test_decode_ce6_records_aux_flags(self) -> None:
        ce6_read0, ce6_read1 = load_ce6_fixture_records()[2:4]

        self.assertEqual(ce6_read0.kind, FtKind.CE6_READ)
        self.assertEqual(ce6_read0.addr, 0x0000)
        self.assertEqual(ce6_read0.data, 0x00)
        self.assertTrue(ce6_read0.aux.rw)
        self.assertFalse(ce6_read0.aux.oe)
        self.assertFalse(ce6_read0.aux.ce1)
        self.assertTrue(ce6_read0.aux.ce6)
        self.assertTrue(ce6_read0.aux.change_record)

        self.assertEqual(ce6_read1.kind, FtKind.CE6_READ)
        self.assertEqual(ce6_read1.addr, 0x0021)
        self.assertEqual(ce6_read1.data, 0xA7)
        self.assertTrue(ce6_read1.aux.rw)
        self.assertFalse(ce6_read1.aux.oe)
        self.assertFalse(ce6_read1.aux.ce1)
        self.assertTrue(ce6_read1.aux.ce6)
        self.assertFalse(ce6_read1.aux.same_addr)
        self.assertFalse(ce6_read1.aux.same_data)
        self.assertTrue(ce6_read1.aux.change_record)

    def test_reassemble_fixture_from_bytes(self) -> None:
        records = list(iter_ft_records_from_bytes(FIXTURE_PATH.read_bytes()))
        self.assertEqual(len(records), 5)
        self.assertEqual(records[2].kind, FtKind.CE1_WRITE)
        self.assertEqual(records[3].kind, FtKind.CE1_WRITE)
        self.assertEqual(records[4].kind, FtKind.CE1_READ)

    def test_timed_records_accumulate_delta(self) -> None:
        timed = list(iter_timed_records(load_fixture_records()))
        self.assertEqual([item.tick for item in timed], [0, 1, 7011, 7019, 7063])

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
    def test_build_vcd_for_raw_bus_changes_and_meta_records(self) -> None:
        records = load_fixture_records() + load_ce6_fixture_records()[2:4] + [load_overflow_fixture_record()]
        vcd = build_vcd(records)

        self.assertIn("$var wire 18", vcd)
        self.assertIn("bus_addr", vcd)
        self.assertIn("event_bus_change", vcd)
        self.assertIn("event_idle_change", vcd)
        self.assertIn("event_ce1_read", vcd)
        self.assertIn("event_overflow", vcd)
        self.assertIn("event_ce6_read", vcd)

        # Time points are in ns with 10 ns per tick.
        self.assertIn("#10", vcd)      # config at 1 tick
        self.assertIn("#70110", vcd)   # write at 7011 ticks
        self.assertIn("#70190", vcd)   # write data settles at 7019 ticks
        self.assertIn("#70630", vcd)   # read tail transition at 7063 ticks

        # Access values get pushed into bus vectors.
        self.assertIn("b000000000100100011", vcd)  # addr 0x123 on 18-bit bus
        self.assertIn("b01011010", vcd)          # data 0x5A
        self.assertIn("b000000000000100001", vcd)  # addr 0x021 on 18-bit bus
        self.assertIn("b10100111", vcd)            # data 0xA7

        # Meta/config values are represented too.
        self.assertIn("b000000000000110010", vcd)  # classify delay 50 ticks
        self.assertIn(f"b{298:026b}", vcd)

    def test_build_vcd_allows_zero_delta_records(self) -> None:
        records = load_fixture_records()
        same_time_records = [
            records[0],
            records[1],
            records[2],
            replace(records[3], delta_ticks=0),
        ]

        vcd = build_vcd(same_time_records)

        self.assertIn("#70110", vcd)
        self.assertIn("#70120", vcd)


if __name__ == "__main__":
    unittest.main()
