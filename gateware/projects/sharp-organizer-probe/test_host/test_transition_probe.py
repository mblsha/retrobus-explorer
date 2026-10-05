import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from organizer_probe import Snapshot
from transition_probe import capture, load_plan


class FakeProbe:
    protocol = "OBP5"
    burst_phase_ns = 5000
    burst_request_bytes = 3
    ft600 = None
    port = SimpleNamespace(baudrate=4_000_000)

    def __init__(self, *, fail=False, drift=False, pins_wrong=False):
        self.fail, self.drift, self.pins_wrong = fail, drift, pins_wrong
        self.addr = self.ctrl = self.addr_mask = self.ctrl_mask = 0
        self.armed = False
        self.commands, self.bursts = [], []

    def snapshot(self):
        return Snapshot(self.addr ^ int(self.pins_wrong), self.addr % 2, self.ctrl, 0x4d,
                        self.addr, self.addr_mask, self.ctrl, self.ctrl_mask, self.armed)

    def park(self):
        self.armed, self.addr_mask, self.ctrl_mask = False, 0, 0
        self.commands.append(("park",))
        return self.snapshot()

    def unlock(self):
        self.armed = True
        self.commands.append(("unlock",))

    def control(self, value, mask):
        self.ctrl, self.ctrl_mask = value, mask
        self.commands.append(("control", value, mask))

    def address(self, value, mask):
        self.addr, self.addr_mask = value, mask
        self.commands.append(("address", value, mask))

    def burst(self, start, count, idle, active, mask):
        self.bursts.append((start, count, idle, active, mask, list(self.commands)))
        self.commands = []
        if self.fail:
            raise TimeoutError("payload failure")
        data = bytes((start + i) % 2 for i in range(count))
        return bytes([data[0] ^ 1]) + data[1:] if self.drift and len(self.bursts) > 2 else data


class TransitionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.document = {"schema": 1, "reported_model": "operator label", "profiles": [
            {"name": "a16-ci-pulse", "steps": [
                {"operation": "address", "value": "0x10000"},
                {"operation": "control", "value": "0xed"},
                {"operation": "control", "value": "0xe9"},
                {"operation": "control", "value": "0xed"}],
             "read": {"start": 0, "length": 6, "idle_control": "0xff", "active_control": "0xed"}}]}

    def plan(self):
        path = self.root / "input.json"
        path.write_text(json.dumps(self.document))
        return load_plan(path)

    def observations(self, directory):
        with gzip.open(self.root / directory / "observations.jsonl.gz", "rt") as stream:
            return [json.loads(line) for line in stream]

    def test_replay_every_chunk_and_pass_with_separate_equal_contexts(self):
        other = json.loads(json.dumps(self.document["profiles"][0]))
        other["name"] = "a17-ci-pulse"
        other["steps"][0]["value"] = "0x20000"
        self.document["profiles"].append(other)
        probe = FakeProbe()
        report = capture(probe, self.plan(), self.root / "capture")
        self.assertEqual(report["status"], "complete")
        self.assertEqual(len(probe.bursts), 8)
        self.assertEqual(len(report["profiles"]), 2)
        self.assertEqual(len(report["images"]), 1)
        self.assertEqual(report["profiles"][0]["observed_address_period"], 2)
        for index, burst in enumerate(probe.bursts):
            start, count, idle, active, mask, commands = burst
            self.assertEqual((start, count, idle, active, mask), ((index % 2) * 3, 3, 0xff, 0xed, 0xff))
            self.assertEqual(commands[-4:], [("address", 0x10000 if index < 4 else 0x20000, 0xfffff),
                                             ("control", 0xed, 0xff), ("control", 0xe9, 0xff),
                                             ("control", 0xed, 0xff)])
        observations = self.observations("capture")
        self.assertEqual(len(observations), 8)
        self.assertTrue(all(not row["park"]["armed"] and row["park"]["address_oe"] == 0 for row in observations))
        self.assertEqual(observations[0]["sequence"][-1]["observed"]["protected_input_pins"]["NC44"], 1)

    def test_failure_retained_and_no_retry(self):
        probe = FakeProbe(fail=True)
        with self.assertRaisesRegex(TimeoutError, "payload failure"):
            capture(probe, self.plan(), self.root / "failed")
        report = json.loads((self.root / "failed/manifest.json").read_text())
        self.assertEqual(report["status"], "failed")
        self.assertFalse(report["final_park"]["armed"])
        self.assertEqual(len(probe.bursts), 1)
        self.assertFalse(list((self.root / "failed").glob("*.bin")))
        row = self.observations("failed")[0]
        self.assertEqual(row["status"], "failed")
        self.assertEqual(row["sequence"][-1]["value"], 0xed)

    def test_pass_disagreement_is_not_promoted(self):
        with self.assertRaisesRegex(RuntimeError, "differs at 0x00000"):
            capture(FakeProbe(drift=True), self.plan(), self.root / "mismatch")
        report = json.loads((self.root / "mismatch/manifest.json").read_text())
        self.assertEqual(report["images"], [])
        row = self.observations("mismatch")[-1]
        self.assertEqual(row["mismatch_address"], 0)

    def test_observed_pin_mismatch_aborts_before_burst(self):
        probe = FakeProbe(pins_wrong=True)
        with self.assertRaisesRegex(RuntimeError, "observed pins differ"):
            capture(probe, self.plan(), self.root / "pins")
        self.assertEqual(probe.bursts, [])
        self.assertFalse(probe.armed)
        row = self.observations("pins")[0]
        self.assertEqual(row["sequence"][-1]["operation"], "address")
        self.assertEqual(row["sequence"][-1]["status"], "started")

    def test_reject_unsafe_controls_unknown_outputs_and_watchdog_holds(self):
        for operation, value in (("control", 0xec), ("control", 0x8f),
                                 ("data", 0), ("NC02", 1), ("address", 1 << 20),
                                 ("hold_us", 100_001)):
            with self.subTest(operation=operation, value=value):
                self.document["profiles"][0]["steps"] = [{"operation": operation, "value": value}]
                with self.assertRaises(ValueError):
                    self.plan()

    def test_reject_bad_read_and_duplicate_json_keys(self):
        self.document["profiles"][0]["read"]["active_control"] = 0xff
        with self.assertRaises(ValueError):
            self.plan()
        path = self.root / "duplicate.json"
        path.write_text('{"schema": 1, "schema": 1}')
        with self.assertRaisesRegex(ValueError, "duplicate JSON"):
            load_plan(path)

    def test_held_read_preserves_control_after_preamble(self):
        self.document["profiles"][0]["read"]["mode"] = "held_select"
        probe = FakeProbe()
        probe.burst_request_bytes = 6
        report = capture(probe, self.plan(), self.root / "held")
        self.assertEqual(probe.bursts, [])
        self.assertEqual(report["profiles"][0]["mode"], "held_select")
        self.assertEqual((self.root / "held/bank-00.bin").read_bytes(), b"\x00\x01")
        rows = self.observations("held")
        self.assertEqual(len(rows), 2)
        self.assertEqual([sample["address"] for sample in rows[0]["held_samples"]], list(range(6)))
        self.assertTrue(all(sample["control"] == 0xed for row in rows for sample in row["held_samples"]))
        # The only control commands are initialization plus the declared preamble.
        self.assertEqual([item for item in probe.commands if item[0] == "control"],
                         [("control", value, 0xff) for value in (0xff, 0xed, 0xe9, 0xed)] * 2)

    def test_held_read_rejects_preamble_ending_deselected(self):
        self.document["profiles"][0]["read"]["mode"] = "held_select"
        self.document["profiles"][0]["steps"].append({"operation": "control", "value": 0xff})
        with self.assertRaisesRegex(ValueError, "preamble must end"):
            self.plan()


if __name__ == "__main__":
    unittest.main()
