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

    def recv(self, size):
        if self.drop:
            self.drop = False
            raise socket.timeout()
        result = reply(self.sent[-1], self.status)
        if self.corrupt:
            self.corrupt = False
            result = result[:-1] + bytes([result[-1] ^ 1])
        return result


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
        self.assertEqual(len(sock.sent), 2)
        self.assertEqual(sock.sent[0], sock.sent[1])
        self.assertEqual(client.sequence, 8)
        self.assertEqual(client.retries, 1)

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
                resumed = images.Images(state=path)
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
                resumed = images.Images(state=path)
                resumed.command(images.Opcode.DISARM)
                self.assertEqual([request[4] for request in sock.sent], [2, 5])
                self.assertEqual(resumed.sequence, 9)
                self.assertIsNone(resumed.pending)

    def test_upload_verification_precedes_arm(self):
        client = object.__new__(images.Images)
        calls = []
        client.begin = lambda n: calls.append(("begin", n))
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
                super().send(request)
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
        client = object.__new__(images.Images)
        calls = []
        image = bytes(range(256)) * 4
        client.begin = lambda count: calls.append(("begin", count))
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


if __name__ == "__main__":
    unittest.main()
