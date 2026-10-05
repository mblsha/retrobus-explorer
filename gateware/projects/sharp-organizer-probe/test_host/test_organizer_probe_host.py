"""Check the client framing and its release-on-exit read sequence."""

import sys
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from organizer_probe import Probe, Snapshot, cycle, read_burst, run_dump, validate_cycle, verify_committed_backup


class FakePort:
    def __init__(self, responses):
        self.responses = list(responses)
        self.pending = b""
        self.requests = []

    def write(self, request):
        self.requests.append(request)
        self.pending = self.responses.pop(0)
        return len(request)

    def flush(self):
        pass

    def reset_input_buffer(self):
        self.pending = b""

    def read(self, size):
        result, self.pending = self.pending[:size], self.pending[size:]
        return result


SNAPSHOT = bytes.fromhex("53 00 01 23 a5 80 00 00 01 23 0f ff ff 80 80 01")
RELEASED_SNAPSHOT = b"S" + bytes(15)


class ProbeHostTest(unittest.TestCase):
    def test_short_read_retries_same_range_after_verified_release(self):
        fake = FakePort([b"U", b"R\x10", b"Z", RELEASED_SNAPSHOT, b"U", b"R\x10\x11"])
        probe = Probe(fake)
        self.assertEqual(read_burst(probe, 0x123, 2, 0xff, 0x7d, 0xff), b"\x10\x11")
        self.assertEqual(fake.requests[1], fake.requests[5])
        self.assertEqual(fake.requests[2:4], [b"Z", b"?"])
        self.assertEqual(probe.read_retry_events[0]["start"], 0x123)
        self.assertEqual(probe.read_retry_events[0]["active_control"], 0x7d)
        self.assertEqual(len(probe.read_retry_events), 1)

    def test_read_retry_stops_if_release_is_not_verified(self):
        fake = FakePort([b"U", b"R\x10", b"Z", SNAPSHOT])
        with self.assertRaisesRegex(RuntimeError, "still driving"):
            read_burst(Probe(fake), 0x123, 2, 0xff, 0x7d, 0xff)
        self.assertEqual(fake.requests[-1], b"?")
        self.assertEqual(fake.requests.count(b"UREAD"), 1)

    def test_read_retries_are_bounded_and_never_accept_short_payload(self):
        fake = FakePort([b"U", b"R\x10", b"Z", RELEASED_SNAPSHOT] * 2 + [b"U", b"R\x10"])
        probe = Probe(fake)
        with self.assertRaisesRegex(TimeoutError, "1/2 bytes"):
            read_burst(probe, 0x123, 2, 0xff, 0x7d, 0xff)
        self.assertEqual(fake.requests.count(b"UREAD"), 3)
        self.assertEqual(len(probe.read_retry_events), 2)

    def test_context_releases_and_verifies_pins_on_exit(self):
        fake = FakePort([b"Z", RELEASED_SNAPSHOT])
        probe = Probe(fake)
        probe.protocol = "OBP4"
        with probe:
            pass
        self.assertEqual(fake.requests, [b"Z", b"?"])

    def test_context_releases_on_command_error(self):
        fake = FakePort([b"Z", RELEASED_SNAPSHOT])
        probe = Probe(fake)
        probe.protocol = "OBP4"
        with self.assertRaisesRegex(ValueError, "command failed"):
            with probe:
                raise ValueError("command failed")
        self.assertEqual(fake.requests, [b"Z", b"?"])

    def test_park_rejects_still_driven_pins(self):
        fake = FakePort([b"Z", SNAPSHOT])
        probe = Probe(fake)
        with self.assertRaisesRegex(RuntimeError, "still driving"):
            probe.park()

    def test_adjustable_read_timing_framing(self):
        fake = FakePort([b"T"])
        probe = Probe(fake)
        probe.protocol = "OBP3"
        probe.set_read_timing(1000)
        self.assertEqual(fake.requests, [b"T\x14"])
        self.assertEqual(probe.burst_phase_ns, 1000)
        with self.assertRaisesRegex(ValueError, "50 ns steps"):
            probe.set_read_timing(1025)

    def test_cycle_wire_order_and_decode(self):
        fake = FakePort([b"U", b"C", b"A", b"C", SNAPSHOT, b"C", b"Z"])
        probe = Probe(fake)
        probe.unlock()
        sample = cycle(probe, 0x123, 0x00, 0x80, 0x80, 0)
        probe.release()
        self.assertEqual(sample.data, 0xA5)
        self.assertEqual(fake.requests, [
            b"UREAD", b"C\x00\x80", b"A\x00\x01\x23\x0f\xff\xff",
            b"C\x80\x80", b"?", b"C\x00\x80", b"Z",
        ])

    def test_dump_mismatch_still_releases_and_writes_no_image(self):
        fake = FakePort([b"U", b"R\xa5", b"U", b"R\xa4", b"Z"])
        with self.subTest("comparison"):
            from tempfile import TemporaryDirectory

            with TemporaryDirectory() as directory:
                args = SimpleNamespace(start=0x123, length=1, passes=2,
                                       idle=0x01, active=0x81, mask=0x81,
                                       settle_us=0, slow=False,
                                       output=Path(directory) / "card.bin")
                with self.assertRaisesRegex(RuntimeError, "read mismatch"):
                    run_dump(Probe(fake), args)
                self.assertFalse(args.output.exists())
        self.assertEqual(fake.requests[-1], b"Z")
        self.assertEqual(fake.requests[1], b"R\x00\x01\x23\x00\x01\x01\x81\x81")

    def test_dump_uses_configured_request_size_without_skipping_bytes(self):
        import json
        from tempfile import TemporaryDirectory

        replies = [b"U", b"R\x10\x11", b"U", b"R\x12\x13", b"U", b"R\x14"]
        fake = FakePort(replies * 2 + [b"Z"])
        probe = Probe(fake)
        probe.burst_request_bytes = 2
        with TemporaryDirectory() as directory:
            args = SimpleNamespace(start=0x123, length=5, passes=2,
                                   idle=0x01, active=0x81, mask=0x81,
                                   settle_us=0, slow=False, output=Path(directory) / "card.bin")
            run_dump(probe, args)
            self.assertEqual(args.output.read_bytes(), bytes(range(0x10, 0x15)))
            metadata = json.loads(args.output.with_suffix(".bin.json").read_text())
            self.assertEqual(metadata["burst_request_bytes"], 2)
        requests = [request for request in fake.requests if request.startswith(b"R")]
        self.assertEqual([(int.from_bytes(r[1:4], "big"), int.from_bytes(r[4:6], "big"))
                          for r in requests], [(0x123, 2), (0x125, 2), (0x127, 1)] * 2)

    def test_invalid_cycle_is_rejected_before_drive(self):
        with self.assertRaises(ValueError):
            validate_cycle(0x80, 0x80, 0x80, 20)
        with self.assertRaises(ValueError):
            validate_cycle(0, 0x100, 0x80, 20)
        self.assertEqual(Snapshot.decode(SNAPSHOT).address_oe, 0xFFFFF)

    def test_write_requires_obp3_and_frames_one_bounded_byte(self):
        fake = FakePort([b"W"])
        probe = Probe(fake)
        with self.assertRaisesRegex(RuntimeError, "OBP3"):
            probe.write_byte(0x7FFF, 0x5A, 2)
        probe.protocol = "OBP3"
        probe.write_byte(0x7FFF, 0x5A, 2)
        self.assertEqual(fake.requests, [b"W\x00\x7f\xff\x5a\x02"])
        with self.assertRaisesRegex(ValueError, "selector"):
            probe.write_byte(0x7FFF, 0x5A, 3)

    def test_profiled_write_rejects_rom_and_frames_ci_e2(self):
        fake = FakePort([b"W"])
        probe = Probe(fake)
        probe.protocol = "OBP4"
        for invalid in (0x7d, 0x9d, 0x1d, 0x13, 0xf3):
            with self.assertRaises(ValueError):
                probe.write_profiled_byte(0x1234, 0xa7, invalid)
        probe.write_profiled_byte(0x1234, 0xa7, 0xd3)
        self.assertEqual(fake.requests, [b"W\x00\x12\x34\xa7\x0d"])

    def test_write_backup_must_match_git_head(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "bank-01.bin"
            sidecar = root / "bank-01.bin.json"
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            image.write_bytes(b"\x12\x34")
            sidecar.write_text('{"sha256":"example"}\n')
            subprocess.run(["git", "-C", str(root), "add", "bank-01.bin", "bank-01.bin.json"], check=True)
            subprocess.run(["git", "-C", str(root), "-c", "user.name=Probe Test",
                            "-c", "user.email=probe@example.invalid", "commit", "-qm", "backup"], check=True)
            verify_committed_backup(image)
            image.write_bytes(b"\x12\x35")
            with self.assertRaisesRegex(ValueError, "differs from HEAD"):
                verify_committed_backup(image)


if __name__ == "__main__":
    unittest.main()
