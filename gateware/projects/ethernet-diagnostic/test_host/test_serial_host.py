import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import images
from test_host.test_images_host import ProtocolPeer, reply


class InfoPeer(ProtocolPeer):
    def send(self, request):
        if request[4] != 9:
            return super().send(request)
        self.sent.append(request)
        words = (0x31494252, 524288, self.session, self.sequence,
                 self.written, self.declared, 11 if self.armed else 14, 0, 0)
        self.queue.append(reply(request, payload=struct.pack("<9I", *words).ljust(512, b"\0")))


class SerialTests(unittest.TestCase):
    def test_parser_partial_frames_noise_overflow_and_resync(self):
        transport = images.SerialTransport.__new__(images.SerialTransport)
        transport.frame = bytearray()
        transport.escaped = transport.collecting = transport.invalid = False
        transport.replies = []
        packet = bytes(range(256)) * 4 + bytes(range(28))
        wire = images.serial_frame(packet)
        transport._feed(b"BIOS text\x7eunfinished\x7d\x7e")
        transport._feed(b"\x7e\x7d\x11\x7e")
        transport._feed(images.serial_frame(bytes(1053)))
        for byte in wire:
            transport._feed(bytes([byte]))
        self.assertEqual(transport.replies, [packet])

    def test_port_opens_without_asserting_reset_lines(self):
        events = []
        class Port:
            def __init__(self, **kwargs):
                events.append(kwargs)
            def open(self):
                events.append((self.port, self.dtr, self.rts))
            def close(self):
                pass
        with patch.dict("sys.modules", serial=SimpleNamespace(Serial=Port)):
            transport = images.SerialTransport("test-uart")
            self.addCleanup(transport.close)
        self.assertIsNone(events[0]["port"])
        self.assertEqual(events[1], ("test-uart", False, False))

    def test_resume_after_lost_write_reply_across_transports(self):
        peer = InfoPeer()
        payload = bytes(range(256)) * 4
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "session.json"
            with patch.object(images.socket, "socket", return_value=peer):
                first = images.Images(state=state)
                first.begin(2)
                first.initial_upload["sha256"] = hashlib.sha256(payload).hexdigest()
                first.save()
                peer.lose_replies = True
                with self.assertRaises(TimeoutError):
                    first.command(images.Opcode.WRITE, 0, 1, payload[:512])
                first.close()
            self.assertEqual(peer.effects, [(2, 0)])
            peer.lose_replies = False
            with patch.object(images, "SerialTransport", return_value=peer):
                resumed = images.Images(state=state, serial_port="fallback")
                self.addCleanup(resumed.close)
                resumed.upload(payload, resume=True)
                self.assertTrue(resumed.initial_upload["verified"])
                resumed.command(images.Opcode.ARM)
            self.assertEqual(peer.effects, [(2, 0), (2, 1), (4, 0)])
            self.assertEqual(peer.memory[0] + peer.memory[1], payload)

    def test_resume_rejects_different_image_before_io(self):
        peer = InfoPeer()
        with patch.object(images.socket, "socket", return_value=peer):
            client = images.Images()
            self.addCleanup(client.close)
            client.initial_upload = dict(sectors=1, sha256="wrong")
            with self.assertRaisesRegex(RuntimeError, "identical"):
                client.upload(bytes(512), resume=True)
        self.assertEqual(peer.sent, [])

    def test_info_does_not_recover_pending_mutation(self):
        peer = InfoPeer()
        with patch.object(images.socket, "socket", return_value=peer):
            client = images.Images()
            self.addCleanup(client.close)
            pending = images.encode(2, 123, 1, count=1)
            client.pending = pending
            before = client.sequence
            self.assertEqual(client.info()["session"], 123)
            self.assertEqual(client.pending, pending)
            self.assertEqual(client.sequence, before)
        self.assertEqual([p[4] for p in peer.sent], [9])

    def test_disarm_without_saved_session(self):
        peer = InfoPeer()
        peer.armed = True
        with patch.object(images.socket, "socket", return_value=peer):
            client = images.Images()
            self.addCleanup(client.close)
            with self.assertRaisesRegex(RuntimeError, "recover-session"):
                client.disarm()
            self.assertEqual(client.session, 0)
            self.assertTrue(peer.armed)
            client.disarm(recover_session=True)
        self.assertFalse(peer.armed)
        self.assertEqual([p[4] for p in peer.sent], [9, 9, 5])

    def test_fresh_disarm_leaves_an_unarmed_old_session_unadopted(self):
        for recover in (False, True):
            with self.subTest(recover_session=recover), tempfile.TemporaryDirectory() as directory:
                peer = InfoPeer()
                self.assertNotEqual(peer.session, 0)
                self.assertFalse(peer.armed)
                state = Path(directory) / "session.json"
                with patch.object(images.socket, "socket", return_value=peer):
                    client = images.Images(state=state)
                    try:
                        client.disarm(recover_session=recover)
                        self.assertEqual((client.session, client.sequence), (0, 0))
                        self.assertIsNone(client.pending)
                        self.assertFalse(state.exists(), "no recovery journal should be written")
                    finally:
                        client.close()
                self.assertEqual([p[4] for p in peer.sent], [9])

    def test_fresh_disarm_rejects_an_armed_card_without_a_session(self):
        peer = InfoPeer()
        peer.session, peer.armed = 0, True
        with patch.object(images.socket, "socket", return_value=peer):
            client = images.Images()
            try:
                with self.assertRaisesRegex(RuntimeError, "no recoverable session"):
                    client.disarm(recover_session=True)
                self.assertEqual((client.session, client.sequence), (0, 0))
                self.assertTrue(peer.armed)
            finally:
                client.close()
        self.assertEqual([p[4] for p in peer.sent], [9])

    def test_recv_keeps_tty_settings_fixed_through_empty_and_partial_reads(self):
        chunks = iter([b"", b"noise\x7eR", b"BA1", b"\x7e"])
        class Port:
            in_waiting = 0
            def __init__(self, **kwargs):
                self.timeout = kwargs["timeout"]
            def __setattr__(self, name, value):
                if name == "timeout" and hasattr(self, "timeout"):
                    raise AssertionError("A live TTY must never be reconfigured")
                object.__setattr__(self, name, value)
            def open(self):
                pass
            def close(self):
                pass
            def read(self, size):
                return next(chunks)
        with patch.dict("sys.modules", serial=SimpleNamespace(Serial=Port)):
            transport = images.SerialTransport("test-uart")
            self.addCleanup(transport.close)
            transport.settimeout(0.01)
            self.assertEqual(transport.recv(2048), b"RBA1")
            self.assertEqual(transport.port.timeout, images.TTY_READ_SECONDS)

    def test_uart_rate_mismatch_is_refused_before_opening_the_device(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "result.json"
            manifest.write_text(json.dumps(dict(serial_image_service=True, serial_baud=500000)))
            with patch.object(images, "SerialTransport") as transport:
                with self.assertRaisesRegex(ValueError, "manifest"):
                    images.Images(serial_port="uart", build_manifest=manifest)
                with self.assertRaisesRegex(ValueError, "manifest"):
                    images.Images(serial_port="uart", baud=500000)
                client = images.Images(serial_port="uart", baud=500000, build_manifest=manifest)
                client.close()
                self.assertEqual(transport.call_count, 1)

    def test_selected_transport_is_recorded_and_remains_advisory_on_resume(self):
        peer = InfoPeer()
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "session.json"
            with patch.object(images, "SerialTransport", return_value=peer):
                client = images.Images(state=state, serial_port="fallback")
                client.begin(1)
                client.close()
            saved = json.loads(state.read_text())
            self.assertEqual(saved["transport"]["backend"], "tty")
            with patch.object(images.socket, "socket", return_value=peer):
                client = images.Images(state=state)
                self.assertEqual(client.session, saved["session"])
                self.assertEqual(client.transport["backend"], "udp")
                client.close()
