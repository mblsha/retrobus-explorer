"""A faster read must match the backup, even if its wrong bytes repeat reliably."""

import json
import sys
import unittest
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from benchmark_card import benchmark_case, load_ram_references, main
from test_card_discovery import MemoryProbe


class TimingProbe(MemoryProbe):
    def __init__(self, fail_fast=False):
        super().__init__()
        self.fail_fast = fail_fast
        self.timings = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.park()

    def park(self):
        self.release()
        return self.snapshot()

    def identify(self):
        pass

    def set_read_timing(self, phase):
        self.burst_phase_ns = phase
        self.timings.append(phase)

    def burst(self, *args):
        result = super().burst(*args)
        return bytes(len(result)) if self.fail_fast and self.burst_phase_ns < 1000 else result


VIEW = {"name": "eprom-ci1-e21", "presence": "read_response_unconfirmed",
        "observed_address_period": 64, "start": 0, "scanned_length": 256,
        "image": "bank-00.bin", "selection": {"active_control": 0x7d}}


class BenchmarkTest(unittest.TestCase):
    def test_current_ram_reference_requires_committed_conservative_evidence(self):
        import hashlib
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bank-01.bin").write_bytes(b"old!")
            current = root / "current.bin"
            current.write_bytes(b"new!")
            sidecar = current.with_suffix(".bin.json")
            metadata = {"passes": 2, "start": 0, "length": 4, "burst_phase_us": 5,
                        "active": 0xbd, "sha256": hashlib.sha256(b"new!").hexdigest()}
            sidecar.write_text(json.dumps(metadata))
            view = {"image": "bank-01.bin", "memory_select": "SRAM2",
                    "selection": {"active_control": 0xbd}}
            manifest = {"views": [view]}
            with patch("benchmark_card.verify_committed_file") as committed:
                images, records = load_ram_references(root, manifest, [f"bank-01.bin={current}"])
                self.assertEqual(images, {"bank-01.bin": b"new!"})
                self.assertEqual([call.args[0] for call in committed.call_args_list], [current.resolve(), sidecar.resolve()])
                self.assertEqual(records[0]["sha256"], metadata["sha256"])
                metadata["passes"] = 1
                sidecar.write_text(json.dumps(metadata))
                with self.assertRaisesRegex(ValueError, "two conservative"):
                    load_ram_references(root, manifest, [f"bank-01.bin={current}"])
                view["memory_select"] = "MSKROM"
                with self.assertRaisesRegex(ValueError, "SRAM-only"):
                    load_ram_references(root, manifest, [f"bank-01.bin={current}"])

    def test_complete_address_mirrors_match_the_baseline(self):
        probe = TimingProbe()
        result = benchmark_case(probe, [(VIEW, probe.rom)], 1000, 17, 256, 2)
        self.assertEqual(result["bytes_checked"], 512)
        self.assertEqual(len(result["reads"]), 2)
        self.assertEqual(result["status"], "matched_committed_baseline")
        self.assertFalse(probe.armed)
        self.assertEqual(probe.writes, [])

    def test_failed_fast_qualification_restores_timing_and_records_failure(self):
        probe = TimingProbe(fail_fast=True)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / VIEW["image"]).write_bytes(probe.rom)
            output = root / "benchmark.json"
            manifest = {"reported_model": "test", "views": [VIEW]}
            argv = ["benchmark_card.py", "--port", "fake", "--baud", "4000000", "--capture-dir", str(root),
                    "--output", str(output), "--case", "500:65535", "--scan-length", "256"]
            with patch("sys.argv", argv), patch("benchmark_card.verify_committed_capture", return_value=manifest), \
                    patch("benchmark_card.open_port", return_value=nullcontext(probe.port)), \
                    patch("benchmark_card.Probe", return_value=probe):
                with self.assertRaisesRegex(RuntimeError, "differs from committed baseline"):
                    main()
            report = json.loads(output.read_text())
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["uart_baud"], 4000000)
            self.assertEqual(report["uart_8n1_payload_limit_bytes_per_second"], 400000)
            self.assertEqual(report["cases"], [])
            self.assertEqual(report["final_read_phase_ns"], 5000)
            self.assertEqual(probe.timings[-1], 5000)
            self.assertFalse(report["final_park"]["armed"])
            self.assertEqual(probe.writes, [])


if __name__ == "__main__":
    unittest.main()
