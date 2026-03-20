from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from e500_ft import (  # noqa: E402
    FT_STREAM_VERSION,
    FtKind,
    config_delay_ticks,
    config_enabled,
    decode_ft_record,
    ft_record_from_words,
    iter_ft_records_from_bytes,
    iter_timed_records,
    overflow_count,
    pack_ft_record,
    pack_ft_words,
    sync_version,
)
from ft_to_vcd import build_vcd  # noqa: E402


def ft_aux(
    *,
    rw: bool = False,
    oe: bool = False,
    ce1: bool = False,
    ce6: bool = False,
    same_addr: bool = False,
    same_data: bool = False,
    classified_after_delay: bool = False,
) -> int:
    return (
        (1 if rw else 0)
        | ((1 if oe else 0) << 1)
        | ((1 if ce1 else 0) << 2)
        | ((1 if ce6 else 0) << 3)
        | ((1 if same_addr else 0) << 4)
        | ((1 if same_data else 0) << 5)
        | ((1 if classified_after_delay else 0) << 6)
    )


class FtDecodeTests(unittest.TestCase):
    def test_decode_sync_record(self) -> None:
        raw = pack_ft_record(FtKind.SYNC, 0, 0, FT_STREAM_VERSION, 0)
        record = decode_ft_record(raw)
        self.assertEqual(record.kind, FtKind.SYNC)
        self.assertEqual(record.delta_ticks, 0)
        self.assertEqual(sync_version(record), FT_STREAM_VERSION)

    def test_decode_config_record(self) -> None:
        raw = pack_ft_record(FtKind.CONFIG, 11, 50, 0, 1)
        record = decode_ft_record(raw)
        self.assertEqual(record.kind, FtKind.CONFIG)
        self.assertEqual(record.delta_ticks, 11)
        self.assertEqual(config_delay_ticks(record), 50)
        self.assertTrue(config_enabled(record))

    def test_decode_access_record_aux_flags(self) -> None:
        raw = pack_ft_record(
            FtKind.CE1_READ,
            73,
            0x0123,
            0x5A,
            ft_aux(rw=True, oe=False, ce1=True, same_addr=True, same_data=True, classified_after_delay=True),
        )
        record = decode_ft_record(raw)
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

    def test_decode_overflow_record(self) -> None:
        count = 0x123456
        raw = pack_ft_record(FtKind.OVERFLOW, 9, count & 0x3FFFF, (count >> 18) & 0xFF, 0)
        record = decode_ft_record(raw)
        self.assertEqual(record.kind, FtKind.OVERFLOW)
        self.assertEqual(overflow_count(record), count)

    def test_reassemble_from_words_and_bytes(self) -> None:
        raw = pack_ft_record(FtKind.CE1_WRITE, 19, 0x0007, 0xA5, ft_aux(ce1=True, classified_after_delay=True))
        words = pack_ft_words(raw)
        record = ft_record_from_words(words)
        self.assertEqual(record.raw, raw)

        payload = b"".join(word.to_bytes(2, "little") for word in words)
        records = list(iter_ft_records_from_bytes(payload))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].raw, raw)

    def test_timed_records_accumulate_delta(self) -> None:
        raws = [
            pack_ft_record(FtKind.SYNC, 0, 0, FT_STREAM_VERSION, 0),
            pack_ft_record(FtKind.CONFIG, 5, 50, 0, 1),
            pack_ft_record(FtKind.CE1_READ, 73, 0x12, 0x5A, ft_aux(rw=True, ce1=True, classified_after_delay=True)),
        ]
        timed = list(iter_timed_records(decode_ft_record(raw) for raw in raws))
        self.assertEqual([item.tick for item in timed], [0, 5, 78])


class FtVcdTests(unittest.TestCase):
    def test_build_vcd_for_access_and_meta_records(self) -> None:
        records = [
            decode_ft_record(pack_ft_record(FtKind.SYNC, 0, 0, FT_STREAM_VERSION, 0)),
            decode_ft_record(pack_ft_record(FtKind.CONFIG, 5, 50, 0, 1)),
            decode_ft_record(
                pack_ft_record(
                    FtKind.CE1_READ,
                    73,
                    0x0123,
                    0x5A,
                    ft_aux(rw=True, oe=False, ce1=True, classified_after_delay=True),
                )
            ),
            decode_ft_record(
                pack_ft_record(
                    FtKind.CE1_WRITE,
                    41,
                    0x0123,
                    0xA5,
                    ft_aux(rw=False, oe=True, ce1=True, same_addr=True, classified_after_delay=True),
                )
            ),
            decode_ft_record(pack_ft_record(FtKind.OVERFLOW, 7, 0x0003, 0x00, 0)),
        ]

        vcd = build_vcd(records)

        self.assertIn("$var wire 18", vcd)
        self.assertIn("bus_addr", vcd)
        self.assertIn("event_ce1_read", vcd)
        self.assertIn("event_overflow", vcd)

        # Time points are in ns with 10 ns per tick.
        self.assertIn("#50", vcd)      # config at 5 ticks
        self.assertIn("#780", vcd)     # read at 78 ticks
        self.assertIn("#1190", vcd)    # write at 119 ticks
        self.assertIn("#1260", vcd)    # overflow at 126 ticks

        # Access values get pushed into bus vectors.
        self.assertIn("b000000000100100011", vcd)  # addr 0x123 on 18-bit bus
        self.assertIn("b01011010", vcd)          # data 0x5A
        self.assertIn("b10100101", vcd)          # data 0xA5

        # Meta/config values are represented too.
        self.assertIn("b000000000000110010", vcd)  # classify delay 50 ticks
        self.assertIn("b00000000000000000000000011", vcd)  # overflow count 3


if __name__ == "__main__":
    unittest.main()
