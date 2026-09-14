import importlib.util
import hashlib
import io
from pathlib import Path
import socket
import struct
import tempfile
import unittest
from unittest.mock import Mock, patch
import zlib

spec = importlib.util.spec_from_file_location(
    "images_host", Path(__file__).resolve().parents[1] / "scripts/images.py"
)
images = importlib.util.module_from_spec(spec)
spec.loader.exec_module(images)


def reply(request, status=0, payload=bytes(512)):
    body = b"RBA1" + bytes([request[4], status]) + request[6:24] + payload
    return body + struct.pack("<I", zlib.crc32(body))


class Socket:
    def __init__(self):
        self.sent = []
        self.timeout = 0.1
        self.status = 0
        self.drop = False
        self.corrupt = False
        self.queue = []

    def bind(self, address):
        self.bound = address

    def connect(self, address):
        self.peer = address

    def settimeout(self, timeout):
        self.timeout = timeout

    def gettimeout(self):
        return self.timeout

    def close(self):
        pass

    def send(self, data):
        self.sent.append(data)
        if self.drop:
            self.drop = False
            return
        result = reply(data, self.status)
        if self.corrupt:
            self.corrupt = False
            result = result[:-1] + bytes([result[-1] ^ 1])
        self.queue.append(result)

    def recv(self, size):
        if not self.queue:
            raise socket.timeout()
        return self.queue.pop(0)


class HostTests(unittest.TestCase):
    def test_encoding_and_validation(self):
        request = images.encode(2, 123, 7, 31, 1, b"hello")
        self.assertEqual(len(request), 540)
        self.assertEqual(
            zlib.crc32(request[:-4]), int.from_bytes(request[-4:], "little")
        )
        self.assertEqual(images.decode(reply(request), request), (0, bytes(512)))
        self.assertIsNone(images.decode(reply(images.encode(2, 123, 8)), request))
        self.assertIsNone(images.decode(reply(request)[:-1], request))

    def test_lost_and_corrupt_reply_retry_identical_request(self):
        sock = Socket()
        sock.drop = True
        sock.corrupt = True
        with patch.object(images.socket, "socket", return_value=sock):
            client = images.Images()
            client.session, client.sequence = 123, 7
            client.command(2, 31, 1, b"hello")
        self.assertEqual(len(sock.sent), 3)
        self.assertEqual(sock.sent[0], sock.sent[1])
        self.assertEqual(client.sequence, 8)
        self.assertEqual(client.retries, 2)

    def test_ordered_error_and_session_file(self):
        sock = Socket()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.json"
            with patch.object(images.socket, "socket", return_value=sock):
                client = images.Images(state=path)
                client.session, client.sequence = 123, 7
                sock.status = 4
                with self.assertRaises(images.RemoteError):
                    client.command(2, 31, 1)
                client.close()
                resumed = images.Images(state=path)
                self.addCleanup(resumed.close)
                self.assertEqual((resumed.session, resumed.sequence), (123, 8))
                sock.status = 3
                with self.assertRaises(images.RemoteError):
                    resumed.command(6)
                self.assertEqual(resumed.sequence, 8)

    def test_restart_recovers_pending_before_new_command(self):
        sock = Socket()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.json"
            with patch.object(images.socket, "socket", return_value=sock):
                client = images.Images(state=path)
                client.session, client.sequence = 123, 7
                with patch.object(client, "exchange", side_effect=TimeoutError):
                    with self.assertRaises(TimeoutError):
                        client.command(2, 31, 1, b"hello")
                client.close()
                resumed = images.Images(state=path)
                self.addCleanup(resumed.close)
                resumed.command(images.Opcode.DISARM)
                self.assertEqual([request[4] for request in sock.sent], [2, 5])
                self.assertEqual(resumed.sequence, 9)
                self.assertIsNone(resumed.pending)

    def test_upload_verification_precedes_arm(self):
        with patch.object(images.socket, "socket", return_value=Socket()):
            client = images.Images()
        client.initial_upload = {"verified": False}
        calls = []

        def begin(n):
            client.initial_upload = {"verified": False}
            calls.append(("begin", n))

        client.begin = begin
        client.command = lambda *args: calls.append(args)
        client.download = lambda n: bytes(512 * n)
        client.upload(bytes(1024))
        self.assertEqual([call[0] for call in calls], ["begin", 2, 2])
        with self.assertRaises(RuntimeError):
            client.upload(b"x" * 512)


class BulkHostTests(unittest.TestCase):
    def test_bulk_out_of_order_loss_duplicates_and_no_journal_writes(self):
        class BulkSocket(Socket):
            def __init__(self):
                super().__init__()
                self.queue = []
                self.lost = False

            def send(self, request):
                self.sent.append(request)
                lba, count = struct.unpack("<II", request[16:24])
                data = b"".join(bytes([n & 255]) * 512 for n in range(lba, lba + count))
                if lba == 2 and not self.lost:
                    self.lost = True
                    return
                self.queue.insert(0, reply(request, payload=data))
                if lba == 0:
                    self.queue.insert(0, reply(request, payload=data))

            def recv(self, size):
                if self.queue:
                    return self.queue.pop(0)
                raise socket.timeout()

        sock = BulkSocket()
        ticks = iter(i * 0.003 for i in range(10000))
        with (
            patch.object(images.socket, "socket", return_value=sock),
            patch.object(images.time, "monotonic", side_effect=lambda: next(ticks)),
        ):
            client = images.Images()
            client.session, client.sequence = 123, 7
            with patch.object(
                client, "save", side_effect=AssertionError("bulk read wrote journal")
            ):
                data = client.bulk_download(5, window=3)
            self.assertEqual(data, b"".join(bytes([n]) * 512 for n in range(5)))
            self.assertEqual(client.sequence, 7)
            self.assertGreaterEqual(client.retries, 1)
            self.assertEqual(sock.timeout, 0.5)
            retries = [
                request
                for request in sock.sent
                if int.from_bytes(request[16:20], "little") == 2
            ]
            self.assertGreaterEqual(len(retries), 2)
            self.assertTrue(all(request == retries[0] for request in retries))

    def test_bulk_errors_and_bounds(self):
        sock = Socket()
        sock.status = 4
        with patch.object(images.socket, "socket", return_value=sock):
            client = images.Images()
            client.session = 123
            with self.assertRaises(images.RemoteError):
                client.bulk_download(1)
            with self.assertRaises(ValueError):
                client.bulk_download(2, start=524287)
            with self.assertRaises(ValueError):
                client.bulk_download(1, window=0)

    def test_bulk_retry_exhaustion_preserves_request_and_timeout(self):
        sock = Socket()
        ticks = iter(i * 0.1 for i in range(1000))
        with (
            patch.object(images.socket, "socket", return_value=sock),
            patch.object(images.time, "monotonic", side_effect=lambda: next(ticks)),
            patch.object(sock, "recv", side_effect=socket.timeout),
        ):
            client = images.Images(timeout=0.7)
            client.session, client.sequence = 123, 7
            with self.assertRaisesRegex(TimeoutError, "exhausted"):
                client.bulk_download(1)
            self.assertEqual(len(sock.sent), 13)
            self.assertTrue(all(request == sock.sent[0] for request in sock.sent))
            self.assertEqual(client.retries, 12)
            self.assertEqual(client.sequence, 7)
            self.assertEqual(sock.timeout, 0.7)
            self.assertIsNone(client.pending)

    def test_bulk_remote_error_restores_timeout(self):
        sock = Socket()
        sock.status = 4
        with patch.object(images.socket, "socket", return_value=sock):
            client = images.Images(timeout=0.7)
            client.session, client.sequence = 123, 7
            with self.assertRaises(images.RemoteError) as error:
                client.bulk_download(1)
            self.assertEqual(error.exception.status, 4)
            self.assertEqual(sock.timeout, 0.7)
            self.assertEqual(client.sequence, 7)

    def test_bulk_upload_verifies_after_ordered_writes(self):
        with patch.object(images.socket, "socket", return_value=Socket()):
            client = images.Images()
        client.initial_upload = {"verified": False}
        calls = []
        image = bytes(range(256)) * 4

        def begin(count):
            client.initial_upload = {"verified": False}
            calls.append(("begin", count))

        client.begin = begin
        client.command = lambda *args: calls.append(args)

        def readback(count, window):
            calls.append(("verify", count, window))
            return image

        client.bulk_download = readback
        client.upload(image, window=10)
        self.assertEqual(
            calls,
            [
                ("begin", 2),
                (2, 0, 1, image[:512]),
                (2, 1, 1, image[512:]),
                ("verify", 2, 10),
            ],
        )
        client.bulk_download = lambda count, window: bytes(count * 512)
        with self.assertRaisesRegex(RuntimeError, "readback differs"):
            client.upload(image, window=10)

    def test_compact_wire_bytes_match_padded_header(self):
        padded = images.encode(7, 0x12345678, 0xFFFFFFFF, 524287, 1)
        compact = images.encode(7, 0x12345678, 0xFFFFFFFF, 524287, 1, compact=True)
        self.assertEqual(compact[:24], padded[:24])
        self.assertEqual(
            compact[:24],
            b"RBS1\x07\0\0\0" + struct.pack("<IIII", 0x12345678, 0xFFFFFFFF, 524287, 1),
        )
        self.assertEqual(padded[24:-4], bytes(512))
        with self.assertRaises(ValueError):
            images.encode(7, 123, 9, data=b"x", compact=True)

    def test_compact_read_request(self):
        request = images.encode(7, 123, 9, 0, 2, compact=True)
        self.assertEqual(len(request), 28)
        self.assertEqual(
            zlib.crc32(request[:-4]), int.from_bytes(request[-4:], "little")
        )
        with self.assertRaises(ValueError):
            images.encode(2, 123, 9, compact=True)

    def test_bulk_reply_length_and_crc(self):
        request = images.encode(7, 123, 9, 0, 2)
        data = bytes(1024)
        self.assertEqual(
            images.decode(reply(request, payload=data), request), (0, data)
        )
        self.assertIsNone(images.decode(reply(request), request))
        self.assertEqual(images.decode(reply(request, 4), request), (4, bytes(512)))


class ReadOnlyIntentTests(unittest.TestCase):
    def test_reads_and_status_never_replay_pending_mutation(self):
        for pending_opcode in (
            images.Opcode.WRITE,
            images.Opcode.ARM,
            images.Opcode.DISARM,
        ):
            for operation in (
                lambda c: c.download(1),
                lambda c: c.bulk_download(1),
                lambda c: c.command(images.Opcode.STATUS),
            ):
                with self.subTest(opcode=pending_opcode, operation=operation):
                    sock = Socket()
                    with patch.object(images.socket, "socket", return_value=sock):
                        client = images.Images()
                    client.session = 123
                    client.pending = images.encode(pending_opcode, 123, 1)
                    pending = client.pending
                    with self.assertRaisesRegex(RuntimeError, "Pending mutating"):
                        operation(client)
                    self.assertEqual(sock.sent, [])
                    self.assertEqual(client.pending, pending)

    def test_help_and_invalid_arguments_do_not_open_socket(self):
        for arguments, status in (
            (["--help"], 0),
            (["-h"], 0),
            (["--state", "unused", "--status", "--dry-run"], 2),
            (["--state", "unused", "--status", "--typo"], 2),
        ):
            with (
                self.subTest(arguments=arguments),
                patch("sys.argv", ["images", *arguments]),
                patch.object(images, "Images") as client,
            ):
                with self.assertRaises(SystemExit) as result:
                    images.main()
                self.assertEqual(result.exception.code, status)
                client.assert_not_called()


class BenchmarkTests(unittest.TestCase):
    def test_hash_and_cached_reply_checks_are_operational_guards(self):
        spec = importlib.util.spec_from_file_location(
            "benchmark_reads", Path(images.__file__).with_name("benchmark_reads.py")
        )
        benchmark = importlib.util.module_from_spec(spec)
        with patch.dict("sys.modules", {"images": images}):
            spec.loader.exec_module(benchmark)
        expected = bytes(512)
        arguments = [
            "benchmark",
            "--state",
            "unused",
            "--blocks",
            "1",
            "--repeats",
            "1",
            "--expected-sha256",
            hashlib.sha256(expected).hexdigest(),
        ]
        for case in ("good", "wrong DDR data", "wrong cached reply"):
            with self.subTest(case=case):
                client = Mock(
                    retries=0, last_request=images.encode(images.Opcode.READ, 123, 1)
                )
                client.download.return_value = (
                    bytes([1]) * 512 if case == "wrong DDR data" else expected
                )
                client.exchange.return_value = (
                    0,
                    b"bad" if case == "wrong cached reply" else expected,
                )
                with (
                    patch.object(benchmark, "Images", return_value=client),
                    patch("sys.argv", arguments),
                    patch("sys.stdout", new_callable=io.StringIO),
                ):
                    if case == "good":
                        benchmark.main()
                    else:
                        with self.assertRaisesRegex(RuntimeError, "differs"):
                            benchmark.main()
                client.close.assert_called_once()
                if case == "wrong DDR data":
                    client.exchange.assert_not_called()


class ProtocolPeer(Socket):
    """Independent ordered peer: effects survive a lost acknowledgement."""

    def __init__(self):
        super().__init__()
        self.session, self.sequence = 123, 1
        self.declared, self.written = 1, 0
        self.armed = False
        self.memory = {}
        self.cached_request = self.cached_reply = None
        self.lose_replies = self.lose_reads = self.bad_readback = False
        self.effects = []

    def send(self, request):
        self.sent.append(request)
        opcode = request[4]
        session, sequence, lba, count = struct.unpack("<IIII", request[8:24])
        payload, status = bytes(512), 0
        if request == self.cached_request:
            response = self.cached_reply
        else:
            if opcode == 1:
                if self.armed:
                    status = 4
                elif not (
                    session
                    and session != self.session
                    and sequence == 0
                    and 1 <= count <= 524288
                ):
                    status = 2 if session != self.session else 3
                else:
                    self.session, self.sequence = session, 1
                    self.declared, self.written = count, 0
            elif session != self.session:
                status = 2
            elif sequence != self.sequence:
                status = 3
            else:
                if opcode == 2:
                    if self.armed:
                        status = 4
                    elif lba != self.written or self.written == self.declared:
                        status = 5
                    else:
                        self.memory[lba] = request[24:536]
                        self.written += 1
                        self.effects.append((opcode, lba))
                elif opcode == 3:
                    payload = (
                        bytes([0xFF]) * 512
                        if self.bad_readback
                        else self.memory.get(lba, bytes(512))
                    )
                elif opcode == 4:
                    if self.armed or self.written != self.declared:
                        status = 8
                    else:
                        self.armed = True
                        self.effects.append((opcode, lba))
                elif opcode == 5:
                    self.armed = False
                self.sequence = (self.sequence + 1) & 0xFFFFFFFF
            response = reply(request, status, payload)
            if status not in (2, 3) and not (opcode == 1 and status):
                self.cached_request, self.cached_reply = request, response
        if not self.lose_replies and not (opcode == 3 and self.lose_reads):
            self.queue.append(response)


class RecoveryPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "session.json"
        self.peer = ProtocolPeer()
        self.factory = patch.object(images.socket, "socket", return_value=self.peer)
        self.factory.start()
        self.addCleanup(self.factory.stop)

    def client(self):
        client = images.Images(state=self.path)
        self.addCleanup(client.close)
        return client

    def test_same_arm_and_write_after_executed_but_lost_reply(self):
        for opcode, arguments in (
            (images.Opcode.ARM, ()),
            (images.Opcode.WRITE, (0, 1, b"hello")),
        ):
            with self.subTest(opcode=opcode):
                self.path.unlink(missing_ok=True)
                self.peer.__init__()
                client = self.client()
                client.session, client.sequence = 123, 1
                client.initial_upload = {
                    "session": 123,
                    "sectors": 1,
                    "sha256": "known",
                    "verified": True,
                }
                if opcode == images.Opcode.ARM:
                    self.peer.written = 1
                self.peer.lose_replies = True
                with self.assertRaises(TimeoutError):
                    client.command(opcode, *arguments)
                pending = client.pending
                client.close()
                self.peer.lose_replies = False
                resumed = self.client()
                before = len(self.peer.sent)
                resumed.command(opcode, *arguments)
                self.assertEqual(self.peer.sent[before:], [pending])
                self.assertEqual(len(self.peer.effects), 1)
                self.assertEqual(resumed.sequence, self.peer.sequence)
                self.assertIsNone(resumed.pending)
                resumed.close()

    def test_unsupported_ordered_opcodes_have_no_side_effects(self):
        client = self.client()
        client.session, client.sequence = 123, 1
        client.pending = images.encode(images.Opcode.WRITE, 123, 1, 0, 1, b"old")
        client.save()
        original = self.path.read_bytes()
        pending = client.pending
        for opcode in (images.Opcode.BEGIN, images.Opcode.BULK_READ, 99):
            with self.subTest(opcode=opcode), self.assertRaises(ValueError):
                client.command(opcode)
            self.assertEqual(self.peer.sent, [])
            self.assertEqual(client.pending, pending)
            self.assertEqual(client.sequence, 1)
            self.assertEqual(self.path.read_bytes(), original)

    def test_failed_or_interrupted_verification_cannot_arm_after_restart(self):
        for mode in ("mismatch", "interrupted"):
            with self.subTest(mode=mode):
                self.path.unlink(missing_ok=True)
                self.peer.__init__()
                self.peer.bad_readback = mode == "mismatch"
                self.peer.lose_reads = mode == "interrupted"
                client = self.client()
                with self.assertRaises((RuntimeError, TimeoutError)):
                    client.upload(b"x" * 512)
                self.assertFalse(client.initial_upload["verified"])
                client.close()
                resumed = self.client()
                sent = len(self.peer.sent)
                with self.assertRaisesRegex(RuntimeError, "not verified"):
                    resumed.command(images.Opcode.ARM)
                self.assertEqual(len(self.peer.sent), sent)
                resumed.close()

    def test_verified_initial_upload_survives_restart_and_later_sd_writes(self):
        client = self.client()
        client.upload(b"x" * 512)
        identity = dict(client.initial_upload)
        client.close()
        resumed = self.client()
        self.assertEqual(resumed.initial_upload, identity)
        resumed.command(images.Opcode.ARM)
        self.peer.memory[0] = b"SD modification".ljust(512, b"\0")
        resumed.command(images.Opcode.DISARM)
        resumed.command(images.Opcode.ARM)
        self.assertTrue(self.peer.armed)
        self.assertEqual(resumed.initial_upload, identity)

    def test_refused_begin_preserves_verified_image_across_restart(self):
        client = self.client()
        client.upload(b"x" * 512)
        client.command(images.Opcode.ARM)
        self.peer.memory[0] = b"SD changes".ljust(512, b"\0")
        identity = dict(client.initial_upload)
        journal = self.path.read_bytes()
        state = (
            self.peer.session,
            self.peer.sequence,
            self.peer.declared,
            self.peer.written,
            self.peer.cached_request,
            self.peer.cached_reply,
        )
        memory = dict(self.peer.memory)
        self.peer.sent.clear()
        with self.assertRaises(images.RemoteError) as error:
            client.upload(b"replacement".ljust(1024, b"\0"))
        self.assertEqual(error.exception.status, 4)
        self.assertEqual(self.path.read_bytes(), journal)
        self.assertEqual(
            (
                self.peer.session,
                self.peer.sequence,
                self.peer.declared,
                self.peer.written,
                self.peer.cached_request,
                self.peer.cached_reply,
            ),
            state,
        )
        self.assertTrue(self.peer.armed)
        client.close()
        resumed = self.client()
        self.assertEqual(resumed.initial_upload, identity)
        resumed.command(images.Opcode.DISARM)
        resumed.command(images.Opcode.ARM)
        self.assertTrue(self.peer.armed)
        self.assertEqual(self.peer.memory, memory)
        self.assertEqual([p[4] for p in self.peer.sent], [1, 5, 4])

    def test_accepted_begin_replaces_verification_record(self):
        client = self.client()
        client.upload(b"x" * 512)
        previous_session = client.session
        client.begin(2)
        self.assertNotEqual(client.session, previous_session)
        expected = dict(session=client.session, sectors=2, sha256=None, verified=False)
        self.assertEqual(client.initial_upload, expected)
        client.close()
        resumed = self.client()
        self.assertEqual(resumed.initial_upload, expected)
        with self.assertRaisesRegex(RuntimeError, "not verified"):
            resumed.command(images.Opcode.ARM)

    def test_lost_begin_ack_cannot_transfer_old_verification(self):
        client = self.client()
        client.upload(b"x" * 512)
        previous_session = client.session
        self.peer.lose_replies = True
        with self.assertRaises(TimeoutError):
            client.begin(2, wait=0)
        self.assertNotEqual(self.peer.session, previous_session)
        client.close()
        self.peer.lose_replies = False
        resumed = self.client()
        self.assertEqual(resumed.session, previous_session)
        with self.assertRaises(images.RemoteError) as error:
            resumed.command(images.Opcode.ARM)
        self.assertEqual(error.exception.status, 2)
        self.assertFalse(self.peer.armed)
        self.assertEqual(self.peer.written, 0)

    def test_invalid_begin_does_not_recover_mutation(self):
        client = self.client()
        client.pending = images.encode(images.Opcode.WRITE, 123, 1, 0, 1, b"pending")
        for blocks in (0, 524289):
            with self.assertRaises(ValueError):
                client.begin(blocks)
        self.assertEqual(self.peer.sent, [])
        self.assertIsNotNone(client.pending)

    def test_session_lock_is_held_until_close(self):
        first = self.client()
        with self.assertRaisesRegex(RuntimeError, "already in use"):
            self.client()
        first.close()
        second = self.client()
        second.close()

    def test_stale_packet_does_not_extend_deadline(self):
        now = [0.0]
        client = self.client()
        client.socket.settimeout(1.0)
        request = images.encode(images.Opcode.STATUS, 123, 1)
        calls = []

        def receive(size):
            calls.append(client.socket.gettimeout())
            if len(calls) == 1:
                now[0] = 0.9
                return b"stale"
            now[0] += client.socket.gettimeout()
            raise socket.timeout()

        with (
            patch.object(images.time, "monotonic", side_effect=lambda: now[0]),
            patch.object(client.socket, "recv", side_effect=receive),
        ):
            with self.assertRaises(TimeoutError):
                client.exchange(request, retries=1)
        self.assertAlmostEqual(now[0], 1.0)
        self.assertAlmostEqual(calls[1], 0.1)
        self.assertEqual(client.socket.gettimeout(), 1.0)

    def test_atomic_download_preserves_previous_file_on_write_failure(self):
        output = Path(self.temp.name) / "backup.img"
        output.write_bytes(b"old")
        with patch.object(images.os, "fsync", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                images.atomic_download(output, b"new")
        self.assertEqual(output.read_bytes(), b"old")
        self.assertEqual(list(output.parent.iterdir()), [output])
        images.atomic_download(output, b"new")
        self.assertEqual(output.read_bytes(), b"new")

    def test_irrelevant_cli_arguments_do_not_open_client(self):
        for args in (
            ("--upload", "image", "--start", "0"),
            ("--status", "--bulk"),
            ("--download", "out", "--blocks", "1", "--window", "2"),
        ):
            with (
                patch("sys.argv", ["images", "--state", "unused", *args]),
                patch.object(images, "Images") as create,
                patch("sys.stderr", new_callable=io.StringIO),
            ):
                with self.assertRaises(SystemExit) as result:
                    images.main()
                self.assertEqual(result.exception.code, 2)
                create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
