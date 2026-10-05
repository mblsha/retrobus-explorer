"""Check the client framing and its release-on-exit read sequence."""

import sys
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from organizer_probe import Probe, Snapshot, cycle, read_burst, run_dump, validate_cycle, verify_committed_backup


class FakePort:
    def __init__(self, responses):
        self.responses = list(responses)
        self.pending = b""
        self.requests = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

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
    def test_obp6_nc_drive_and_extended_snapshot(self):
        fake = FakePort([b"OBP6\n", b"N", SNAPSHOT + b"\x09\x0f", b"Z", RELEASED_SNAPSHOT + b"\x00\x00"])
        probe = Probe(fake)
        probe.identify()
        probe.nc(9, 15)
        sample = probe.snapshot()
        self.assertEqual((sample.nc_drive, sample.nc_oe), (9, 15))
        probe.park()
        self.assertEqual(fake.requests, [b"I", b"N\x09\x0f", b"Q", b"Z", b"Q"])

    def test_nc_drive_rejects_legacy_and_out_of_range_before_uart(self):
        fake = FakePort([])
        probe = Probe(fake)
        probe.protocol = "OBP5"
        with self.assertRaisesRegex(RuntimeError, "OBP6"):
            probe.nc(9, 15)
        probe.protocol = "OBP6"
        for value, mask in ((16, 15), (0, 16), (-1, 0)):
            with self.assertRaises(ValueError):
                probe.nc(value, mask)
        self.assertEqual(fake.requests, [])

    def test_park_rejects_a_remaining_nc_output_mask(self):
        fake = FakePort([b"Z", RELEASED_SNAPSHOT + b"\x09\x01"])
        probe = Probe(fake)
        probe.protocol = "OBP6"
        with self.assertRaisesRegex(RuntimeError, "still driving"):
            probe.park()

    def test_ft600_burst_ack_is_uart_and_payload_uses_ft600(self):
        fake = FakePort([b"OBP5\n", b"F"])
        ft600 = Mock()
        ft600.read_payload.return_value = b"abc"
        probe = Probe(fake, ft600)
        probe.identify()
        self.assertEqual(probe.burst(0x123, 3, 0xff, 0x7d, 0xff), b"abc")
        self.assertEqual(fake.requests[-1], b"F\x00\x01\x23\x00\x03\xff\x7d\xff")
        ft600.read_payload.assert_called_once_with(3, 5000)

    def test_ft600_burst_rejects_older_gateware_before_request(self):
        fake = FakePort([])
        probe = Probe(fake, Mock())
        probe.protocol = "OBP4"
        with self.assertRaisesRegex(RuntimeError, "OBP5"):
            probe.burst(0, 1, 0xff, 0x7d, 0xff)
        self.assertEqual(fake.requests, [])

    def test_ft600_chunk_limit_is_applied_and_overflow_never_sent(self):
        fake = FakePort([])
        probe = Probe(fake, Mock())
        probe.protocol = "OBP5"
        self.assertEqual(probe.burst_request_bytes, 8191)
        probe.burst_request_bytes = 4096
        self.assertEqual(probe.burst_request_bytes, 4096)
        probe.burst_request_bytes = 65535
        self.assertEqual(probe.burst_request_bytes, 8191)
        with self.assertRaisesRegex(ValueError, "8191"):
            probe.burst(0, 8192, 0xff, 0x7d, 0xff)
        self.assertEqual(fake.requests, [])

    def test_ft600_failures_never_replay_a_possibly_queued_burst(self):
        for acknowledgement, error in ((b"", TimeoutError), (b"F", OSError)):
            with self.subTest(acknowledgement=acknowledgement):
                fake = FakePort([b"U", acknowledgement])
                ft600 = Mock()
                ft600.read_payload.side_effect = OSError("bad FT payload")
                probe = Probe(fake, ft600)
                probe.protocol = "OBP5"
                with self.assertRaises(error):
                    read_burst(probe, 0, 3, 0xff, 0x7d, 0xff)
                self.assertEqual(len(fake.requests), 2)
                self.assertEqual(probe.read_retry_events, [])

    def test_cli_explicitly_restores_default_hardware_read_timing(self):
        import json
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from organizer_probe import main

        fake = FakePort([b"OBP4\n", b"T", b"U", b"R\x10", b"U", b"R\x10",
                         b"Z", b"Z", RELEASED_SNAPSHOT])
        with TemporaryDirectory() as directory:
            output = Path(directory) / "read.bin"
            argv = ["organizer_probe.py", "--port", "fake", "dump", "--length", "1",
                    "--idle", "0xff", "--active", "0x7d", "--mask", "0xff",
                    "--output", str(output)]
            with patch("sys.argv", argv), patch("organizer_probe.open_port", return_value=fake):
                main()
            self.assertEqual(fake.requests[:2], [b"I", b"T\x64"])
            self.assertEqual(json.loads(output.with_suffix(".bin.json").read_text())["burst_phase_us"], 5.0)

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
