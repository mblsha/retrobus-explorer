import ast
from pathlib import Path
import struct
import unittest
import zlib
from microsd_probe import PROFILES, request, crc8
from microsd_image import packet, decode_ack
from microsd_verify_linux_rw import CAPACITY, CASES, expected_bytes, write_cases
from microsd_stress_linux import payload


class HostTests(unittest.TestCase):
    def test_stress_patterns_distinguish_address_generation_and_seed(self):
        samples = [
            payload(a, g, s)
            for a in (0, 1, 2047, 65535)
            for g in (0, 1, 123)
            for s in (0, 20260908)
        ]
        self.assertEqual(len(set(samples)), len(samples))
        self.assertTrue(all(len(x) == 4096 for x in samples))
        self.assertEqual(payload(65535, 123, 20260908), samples[-1])
        for a, g, s in ((65536, 0, 0), (-1, 0, 0), (0, 1 << 32, 0), (0, 0, -1)):
            with self.assertRaises(AssertionError):
                payload(a, g, s)

    def test_raw_write_plan_is_bounded_and_patterns_are_complements(self):
        self.assertEqual(CAPACITY, 8 * 1024 * 1024)
        self.assertIn((CAPACITY - 512, 512), CASES)
        self.assertLess(sum(size for _, size in CASES) * 2, 65536)
        for offset, size in CASES:
            first = expected_bytes(offset, size, 0)
            second = expected_bytes(offset, size, 1)
            self.assertEqual(len(first), size)
            self.assertTrue(all(a ^ b == 255 for a, b in zip(first, second)))
        for offset, size in ((-512, 512), (CAPACITY, 512), (1, 512), (0, 513)):
            with self.assertRaises(AssertionError):
                expected_bytes(offset, size, 0)

    def test_full_capacity_plan_reaches_last_sector(self):
        capacity = 256 << 20
        self.assertIn((capacity - 512, 512), write_cases(capacity))
        self.assertEqual(len(expected_bytes(capacity - 512, 512, 0, capacity)), 512)
        with self.assertRaises(AssertionError):
            expected_bytes(capacity, 512, 0, capacity)

    def test_profiles_match_pcb_source(self):
        source = (
            Path(__file__).resolve().parents[2]
            / "jitx-py/microsd-pmod-breakout/src/main.py"
        )
        values = {}
        for statement in ast.parse(source.read_text()).body:
            if isinstance(statement, ast.Assign):
                for target in statement.targets:
                    if isinstance(target, ast.Name) and target.id in (
                        "BOTTOM_HEADER_SD_TO_PMOD_PIN",
                        "TOP_HEADER_SD_TO_PMOD_PIN",
                    ):
                        values[target.id] = ast.literal_eval(statement.value)
        self.assertEqual(
            PROFILES["bottom-header"], values["BOTTOM_HEADER_SD_TO_PMOD_PIN"]
        )
        self.assertEqual(
            PROFILES["top-header-r180"], values["TOP_HEADER_SD_TO_PMOD_PIN"]
        )

    def test_measured_row_swap_matches_hardware_evidence(self):
        import json

        source = (
            Path(__file__).resolve().parents[1]
            / "docs/hardware/gkd-arty-jd-pinout-2026-09-07.json"
        )
        evidence = json.loads(source.read_text())
        gpio_signals = {
            64: "DAT0",
            65: "DAT1",
            66: "DAT2",
            67: "DAT3",
            68: "CMD",
            69: "CLK",
        }
        physical = (1, 2, 3, 4, 7, 8, 9, 10)
        mapping = PROFILES["bottom-header-row-swap"]
        for row in evidence["records"]:
            self.assertTrue(row["passed"])
            index = physical.index(mapping[gpio_signals[row["linux_gpio"]]])
            expected = (1 << index) if row["drive"] else 0
            self.assertEqual(row["observed_raw"] & evidence["active_mask"], expected)

    def test_packet_bounds_and_crc(self):
        self.assertEqual(crc8(b"123456789"), 0xF4)
        raw = packet(1, 127, 0x12345678, bytes(range(256)) * 2)
        self.assertEqual(len(raw), 532)
        self.assertEqual(struct.unpack("<I", raw[-4:])[0], zlib.crc32(raw[:-4]))
        self.assertEqual(raw[8:16], struct.pack("<II", 127, 0x12345678))
        for sector in (-1, 128):
            with self.assertRaises(ValueError):
                packet(1, sector, 0)
        with self.assertRaises(ValueError):
            request(99, 0)

    def test_ack_corruption(self):
        body = struct.pack("<4sBB2xI", b"MSA1", 1, 0, 123)
        ack = body + struct.pack("<I", zlib.crc32(body))
        self.assertEqual(decode_ack(ack), (1, 0, 123))
        for i in range(16):
            bad = bytearray(ack)
            bad[i] ^= 1
            with self.assertRaises(ValueError):
                decode_ack(bytes(bad))


if __name__ == "__main__":
    unittest.main()
