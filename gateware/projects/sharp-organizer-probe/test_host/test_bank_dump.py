"""Bank selection attribution and staged output of the host dumper."""

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from bank_dump import load_plan, run_plan
from organizer_probe import Probe
from test_organizer_probe_host import FakePort


def plan_document():
    return {
        "schema": 1,
        "card_label": "test card",
        "banks": [
            {"name": "eprom", "start": "0x123", "length": 2,
             "pins": {"RW": [1, 1], "OE": [1, 0], "EPROM": [1, 0]}},
            {"name": "sram1", "start": "0x456", "length": 2,
             "pins": {"RW": [1, 1], "OE": [1, 0], "SRAM1": [1, 0]}},
        ],
    }


def snapshot(address, data, active, mask):
    return (b"S" + address.to_bytes(3, "big") + bytes([data, active, 0x7B])
            + address.to_bytes(3, "big") + (0xFFFFF).to_bytes(3, "big")
            + bytes([active, mask, 1]))


def responses(address, data, active, mask):
    return [b"U", b"C", b"A", b"C", snapshot(address, data[0], active, mask),
            b"C", b"Z", b"U", b"R" + data, b"U", b"R" + data, b"Z"]


class BankDumpTest(unittest.TestCase):
    def test_two_banks_keep_distinct_pin_attribution(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "plan.json"
            path.write_text(json.dumps(plan_document()))
            plan = load_plan(path)
            fake = FakePort(responses(0x123, b"\xa5\x5a", 0x01, 0x83)
                            + responses(0x456, b"\x12\x34", 0x01, 0x23))
            output = root / "bundle"
            manifest = run_plan(Probe(fake), plan, output)
            self.assertEqual((output / "bank-00.bin").read_bytes(), b"\xa5\x5a")
            self.assertEqual((output / "bank-01.bin").read_bytes(), b"\x12\x34")
            self.assertEqual([bank["selection"]["driven_low_during_read"]
                              for bank in manifest["banks"]],
                             [["OE", "EPROM"], ["OE", "SRAM1"]])
            self.assertEqual(manifest["banks"][1]["selection"]["pins"]["EPROM"]["driven"], False)
            self.assertEqual(manifest["banks"][1]["observed_active_preflight"]["control_pins"]["SRAM1"], 0)
            self.assertEqual(json.loads((output / "manifest.json").read_text()), manifest)
            self.assertEqual(json.loads((output / "bank-01.bin.json").read_text())["bank_name"], "sram1")
            self.assertEqual(fake.requests[-1], b"Z")

    def test_bad_rw_and_file_names_are_rejected_before_hardware(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            document = plan_document()
            document["banks"][0]["pins"]["RW"] = [1, 0]
            path.write_text(json.dumps(document))
            with self.assertRaisesRegex(ValueError, "RW high"):
                load_plan(path)
            document["banks"][0]["pins"]["RW"] = [1, 1]
            document["banks"][0]["name"] = "../other"
            path.write_text(json.dumps(document))
            with self.assertRaisesRegex(ValueError, "name must use"):
                load_plan(path)

    def test_mismatch_leaves_no_bundle(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            document = plan_document()
            document["banks"] = document["banks"][:1]
            path = root / "plan.json"
            path.write_text(json.dumps(document))
            mismatch = responses(0x123, b"\xa5\x5a", 0x01, 0x83)
            mismatch[-2] = b"R\xa5\x5b"
            output = root / "bundle"
            with self.assertRaisesRegex(RuntimeError, "read mismatch"):
                run_plan(Probe(FakePort(mismatch)), load_plan(path), output)
            self.assertFalse(output.exists())
            self.assertEqual(list(root.glob(".bundle-*")), [])


if __name__ == "__main__":
    unittest.main()
