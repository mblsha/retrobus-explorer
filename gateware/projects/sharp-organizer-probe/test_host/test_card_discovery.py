"""Discovery, deduplication, committed backup, and bus-echo regressions."""

import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from card_discovery import Selection, address_period, capture, selections, volume_header
from card_write import commit_capture, commit_directory, probe_ram, verify_committed_capture, write_sram
from organizer_probe import Snapshot


class MemoryProbe:
    def __init__(self):
        self.protocol = "OBP4"
        self.port = SimpleNamespace(baudrate=5_000_000)
        self.burst_phase_ns = 5000
        self.rom = bytes(range(64))
        self.sram = bytearray(bytes((index * 7 + 3) & 255 for index in range(32)))
        self.last_data = 0x04
        self.armed = False
        self.address_value = 0
        self.control_value = 0xff
        self.control_mask = 0
        self.writes = []

    def unlock(self):
        self.armed = True

    def release(self):
        self.armed = False
        self.control_mask = 0

    def address(self, value, mask):
        self.address_value = value

    def control(self, value, mask):
        self.control_value = value
        self.control_mask = mask

    def _byte(self, address, active):
        if active & 0x80 == 0:
            result = self.rom[address % len(self.rom)]
        elif active & 0x40 == 0:
            result = self.sram[address % len(self.sram)]
        else:
            result = self.last_data
        self.last_data = result
        return result

    def snapshot(self):
        return Snapshot(self.address_value, self._byte(self.address_value, self.control_value),
                        self.control_value, 0, self.address_value if self.armed else 0,
                        0xfffff if self.armed else 0, self.control_value if self.armed else 0,
                        self.control_mask if self.armed else 0, self.armed)

    def burst(self, start, count, idle, active, mask):
        return bytes(self._byte(start + offset, active) for offset in range(count))

    def write_profiled_byte(self, address, value, selected):
        self.writes.append((address, value, selected))
        if selected & 0x40 == 0:
            self.sram[address % len(self.sram)] = value
        else:
            self.last_data = value
        self.release()


class DiscoveryTest(unittest.TestCase):
    def test_period_and_header_are_hints(self):
        self.assertEqual(address_period(bytes(range(4)) * 64), 4)
        self.assertEqual(address_period(b"\xa5" * 256), 1)
        header = bytearray(32)
        header[:4] = b"\x10\x12\x40\x00"
        header[6:17] = b"S-C12      "
        self.assertEqual(volume_header(header)["capacity_hint_bytes"], 131072)

    def test_all_supported_single_select_states(self):
        states = selections()
        self.assertEqual(len(states), 16)
        self.assertEqual(len({state.name for state in states}), 16)
        self.assertTrue(all(state.active & 1 and state.active & 2 == 0 for state in states))

    def test_capture_deduplicates_views_and_does_not_write(self):
        with TemporaryDirectory() as directory:
            probe = MemoryProbe()
            output = Path(directory) / "capture"
            manifest = capture(probe, output, limit=256, reported_model="test card")
            self.assertEqual(len(manifest["views"]), 16)
            self.assertEqual(len(manifest["images"]), 3)
            self.assertEqual(probe.writes, [])
            self.assertEqual(manifest["reported_model"], "test card")
            rom = next(view for view in manifest["views"] if view["name"] == "eprom-ci1-e21")
            echo = next(view for view in manifest["views"] if view["name"] == "sram1-ci1-e21")
            ram = next(view for view in manifest["views"] if view["name"] == "sram2-ci1-e21")
            self.assertEqual(rom["observed_address_period"], 64)
            self.assertEqual(ram["observed_address_period"], 32)
            self.assertEqual(echo["presence"], "open_bus_or_echo")
            self.assertEqual(rom["mirror_relation"], "verified_full_address_mirror")
            self.assertEqual(manifest["views"][4]["duplicate_data_of"], rom["name"])
            self.assertEqual((output / ram["image"]).read_bytes(), bytes(probe.sram))

    def test_committed_backup_gates_probe_and_sram_write(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "Probe Test"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "probe@example.invalid"], check=True)
            probe = MemoryProbe()
            output = root / "roms/cards/sharp-organizer/fixture"
            capture(probe, output, limit=256)
            with self.assertRaises(ValueError):
                verify_committed_capture(output)
            commit_capture(output)
            verify_committed_capture(output)
            result = probe_ram(probe, output, output / "write-probes")
            outcomes = {item["view"]: item["result"] for item in result["probes"]}
            self.assertEqual(outcomes["sram1-ci1-e21"], "open_bus_or_echo_no_write")
            self.assertEqual(outcomes["sram2-ci1-e21"], "writable_ram_confirmed")
            self.assertEqual(len(probe.writes), 16)
            self.assertEqual(probe.sram, bytearray(bytes((index * 7 + 3) & 255 for index in range(32))))
            self.assertIn("sram2-ci0-e21", result["probes"][1]["physical_aliases_confirmed"])
            self.assertEqual(len(result["physical_alias_groups"]), 1)
            self.assertEqual(len(result["physical_alias_groups"][0]), 4)
            commit_directory(output / "write-probes", "Record simulated SRAM probes")
            payload = root / "payload.bin"
            payload.write_bytes(b"\xa5\x5a")
            written = write_sram(probe, output, output / "write-probes/result.json",
                                 "sram2-ci1-e21", 4, payload.read_bytes(), root / "transaction")
            self.assertEqual(written["status"], "verified")
            self.assertEqual(probe.sram[4:6], b"\xa5\x5a")
            commit_directory(root / "transaction", "Record simulated SRAM write")
            restored = write_sram(probe, output, output / "write-probes/result.json",
                                  "sram2-ci1-e21", 4, bytes((4 * 7 + 3, 5 * 7 + 3)),
                                  root / "restore", root / "transaction/after.bin")
            self.assertEqual(restored["status"], "verified")
            self.assertEqual(probe.sram[4:6], bytes((4 * 7 + 3, 5 * 7 + 3)))


if __name__ == "__main__":
    unittest.main()
