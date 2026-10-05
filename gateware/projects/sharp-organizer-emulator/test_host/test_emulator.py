import ctypes
import importlib.util
import os
import struct
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from functools import reduce
from operator import xor
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/emulator.py"
spec = importlib.util.spec_from_file_location("organizer_emulator_client", SCRIPT)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def reply(op, status=0, payload=b""):
    body = bytes([0xD5, ord(op), status]) + payload.ljust(12, b"\0")
    return body + bytes([reduce(xor, body)])


class FakeSerial:
    def __init__(self, *_args, **_kwargs):
        self.incoming = bytearray()
        self.memory = bytearray(65536)
        self.closed = self.sealed = self.armed = False
        self.operations = []
        self.bad_readback = self.busy_once = False
        self.last_end = 0

    def write(self, frame):
        assert len(frame) == 8 and reduce(xor, frame) == 0
        _, op, address, data, _, _, _ = struct.unpack("<BBHBBBB", frame)
        op = chr(op)
        self.operations.append((op, address, data))
        status, payload = 0, b""
        if op == "I":
            payload = b"OEM1"
        elif op == "S" and address == 0:
            payload = bytes(
                [
                    int(self.armed) | 2 | (int(self.sealed) << 2),
                    5,
                    10,
                    6,
                    0x80,
                    0,
                    0,
                    0,
                    self.last_end,
                ]
            )
        elif op == "R":
            payload = bytes([self.memory[address] ^ int(self.bad_readback)])
        elif op == "W":
            if self.busy_once:
                status = 3
                self.busy_once = False
            else:
                self.memory[address] = data
                if address == tool.SEQUENCE and data:
                    self.last_end = data
        elif op == "V":
            self.sealed = True
        elif op == "A":
            self.armed = True
        elif op == "Z":
            self.armed = False
        self.incoming.extend(reply(op, status, payload))
        return len(frame)

    def read(self, count):
        count = min(count, 3)
        result = bytes(self.incoming[:count])
        del self.incoming[:count]
        return result

    def close(self):
        self.closed = True


class ClientTests(unittest.TestCase):
    def test_frames_detect_wrong_opcode_corruption_and_status(self):
        self.assertEqual(len(tool.request("W", 0x1234, 0x56)), 8)
        self.assertEqual(reduce(xor, tool.request("W", 0x1234, 0x56)), 0)
        self.assertEqual(
            tool.decode_reply(reply("I", payload=b"OEM1"), "I")[:4], b"OEM1"
        )
        for frame in (reply("R"), reply("I")[:-1], reply("I")[:-1] + b"\xff"):
            with self.assertRaises(tool.ProtocolError):
                tool.decode_reply(frame, "I")
        with self.assertRaises(tool.StatusError):
            tool.decode_reply(reply("W", 3), "W")

    def test_memory_bounds_and_busy_retry(self):
        with tool.Client("fake", serial_factory=FakeSerial) as client:
            client.serial.busy_once = True
            client.write(0x87FF, b"\xa5")
            self.assertEqual(client.read(0x87FF, 1), b"\xa5")
            self.assertEqual(
                len([op for op in client.serial.operations if op[0] == "W"]), 2
            )
            for address, size in ((-1, 1), (0x3FFF, 2), (0x8800, 1), (0x8000, -1)):
                with self.assertRaises(ValueError):
                    client.read(address, size)
            self.assertEqual(client.status()["rom_select"], "EPROM")
        self.assertTrue(client.serial.closed)

    def test_full_image_verified_and_sealed_last(self):
        image = bytes(range(256)) * 64
        with tool.Client("fake", serial_factory=FakeSerial) as client:
            result = client.load(image)
            self.assertTrue(result["sealed"])
            self.assertEqual(client.serial.memory[: tool.ROM_SIZE], image)
            self.assertEqual(
                [op[0] for op in client.serial.operations][-3:], ["V", "S", "S"]
            )
            self.assertFalse(result["armed"])
        with tool.Client("fake", serial_factory=FakeSerial) as client:
            client.serial.bad_readback = True
            with self.assertRaises(tool.ProtocolError):
                client.load(image)
            self.assertFalse(client.serial.sealed)

    def test_job_commits_sequence_after_verified_payload_and_body(self):
        with tool.Client("fake", serial_factory=FakeSerial) as client:
            client.serial.armed = True
            result = client.job(b"\x07")
            self.assertEqual(result["sequence"], 1)
            writes = [op for op in client.serial.operations if op[0] == "W"]
            self.assertEqual(writes[0], ("W", tool.SEQUENCE, 0))
            self.assertEqual(writes[-1], ("W", tool.SEQUENCE, 1))
            self.assertEqual(
                client.serial.memory[tool.MAILBOX : tool.MAILBOX + 3], b"XR\x01"
            )

    def test_decoder_chunks_gaps_wrap_and_raw_pins(self):
        def event(seq, ticks):
            return struct.pack("<IIII", 0xE7010000 | seq, ticks, 0x17D40234, 0x00101269)

        raw = event(65534, 0xFFFFFFFE) + event(1, 2)
        decoder = tool.TraceDecoder()
        result = []
        for offset in range(0, len(raw), 3):
            result.extend(decoder.feed(raw[offset : offset + 3]))
        decoder.finish()
        self.assertEqual(result[1]["gap_before"], 2)
        self.assertEqual(result[1]["elapsed_ns"], ((1 << 32) + 2) * 10)
        self.assertEqual(result[0]["address"], 0x40234)
        self.assertEqual(result[0]["data"], 0x69)
        self.assertFalse(result[0]["pins"]["OE"])
        self.assertTrue(result[0]["aux_pins"]["NC42"])
        decoder.feed(b"\xe7")
        with self.assertRaises(tool.ProtocolError):
            decoder.finish()
        with self.assertRaises(tool.ProtocolError):
            tool.TraceDecoder().feed(bytes(16))


class FtHostTests(unittest.TestCase):
    def test_pipe_results_use_call_local_status_and_preserve_null_bytes(self):
        ft = object.__new__(tool.Ft600)
        ft.transport = SimpleNamespace(
            _valid_status=(0, 19), dev=SimpleNamespace(handle=1, status=999)
        )

        def read(_handle, _channel, buffer, _size, count, _timeout):
            ctypes.memmove(buffer, b"\0\xff\1\0", 4)
            count._obj.value = 4
            return 0

        def write(_handle, _channel, buffer, size, count, _timeout):
            self.assertEqual(ctypes.string_at(buffer, size.value), b"\0\xff\1\0")
            count._obj.value = 2
            return 19  # Timeout with confirmed partial transfer.

        ft.api = SimpleNamespace(
            ULONG=ctypes.c_uint32,
            UCHAR=ctypes.c_uint8,
            FT_ReadPipeEx=read,
            FT_WritePipeEx=write,
        )
        ft.bindings = SimpleNamespace(call_ft=lambda fn, *args: fn(*args))
        self.assertEqual(ft.read(16), b"\0\xff\1\0")
        self.assertEqual(ft.write(b"\0\xff\1\0"), 2)
        with self.assertRaises(ValueError):
            ft.write(b"x")

    def test_raw_capture_records_incomplete_input_and_exit_policy(self):
        class FakeClient:
            def __init__(self):
                self.stopped = False

            def status(self):
                return {"dropped_records": 0}

            def command(self, op):
                self.stopped = op == "Z"

        class FakeFt:
            transport = SimpleNamespace(serial="test", configuration={"FIFOClock": 0})
            raw = struct.pack("<IIII", 0xE7010000, 1, 0x17D40000, 0x69)

            def read(self):
                time.sleep(0.001)
                raw, self.raw = self.raw, b""
                return raw

            def write(self, _data):
                return 0  # Input backpressure.

        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "input.bin"
            source.write_bytes(b"ab")
            client = FakeClient()
            result = tool.capture(
                client,
                FakeFt(),
                Path(temp) / "capture",
                0.01,
                source,
                stop_on_exit=True,
            )
            self.assertTrue(client.stopped)
            self.assertEqual(result["raw_bytes"], 16)
            self.assertEqual(result["records"], 1)
            self.assertIsNone(result["observed_sequence_gaps"])
            self.assertFalse(result["input_complete"])
            self.assertFalse(result["capture_complete"])
            self.assertEqual((Path(temp) / "capture/trace.bin").stat().st_size, 16)


@unittest.skipUnless(
    os.environ.get("SC62015_ASSEMBLER_ROOT"),
    "set SC62015_ASSEMBLER_ROOT in an assembler environment",
)
class NativeTests(unittest.TestCase):
    def test_resident_loop_magic_sequence_and_smoke_return(self):
        root = Path(os.environ["SC62015_ASSEMBLER_ROOT"])
        sys.path.insert(0, str(root))
        from binja_test_mocks import binja_api  # noqa: F401 - install before importing the CPU
        from binja_test_mocks.eval_llil import Memory
        from sc62015.pysc62015 import CPU, RegisterName
        from sc62015.pysc62015.constants import ADDRESS_SPACE_SIZE

        base = 0x40000
        with tempfile.TemporaryDirectory() as temp:
            supervisor, smoke = Path(temp) / "supervisor.bin", Path(temp) / "smoke.bin"
            meta = tool.build_supervisor(root, base, supervisor)
            tool.build_supervisor(root, base, smoke, "boot_smoke")
            self.assertEqual(meta["entry"], base + 0x100)
            raw = bytearray(ADDRESS_SPACE_SIZE)
            raw[base : base + tool.ROM_SIZE] = supervisor.read_bytes()
            raw[base + 0x400 : base + 0x400 + smoke.stat().st_size] = smoke.read_bytes()
            writes = []
            incoming = []

            def read(address):
                if address == base + 0x3FF7:
                    return int(bool(incoming))
                if address == base + 0x3FF8:
                    return incoming.pop(0) if incoming else 0
                return 1 if address == base + 0x3FFA else raw[address]

            def write(address, value):
                raw[address] = value
                writes.append((address, value))

            memory = Memory(read, write)
            memory.peek_byte_for_preflight = lambda address, _pc=None: raw[address]
            cpu = CPU(memory, reset_on_init=False, backend="python")
            cpu.regs.set(RegisterName.PC, meta["entry"])
            cpu.regs.set(RegisterName.S, 0x2000)
            cpu.regs.set(RegisterName.U, 0x3000)

            def steps(count):
                for _ in range(count):
                    cpu.execute_instruction(cpu.regs.get(RegisterName.PC))

            steps(250)
            self.assertEqual(
                bytes(v for a, v in writes if a == base + 0x3FF1), b"OEM1,READY\r\n"
            )
            raw[base + tool.MAILBOX : base + tool.MAILBOX + 3] = b"XR\x02"
            raw[base + tool.SEQUENCE] = 1
            steps(100)
            self.assertNotIn((base + 0x3FF0, 1), writes)
            raw[base + tool.MAILBOX + 2] = 1
            steps(200)
            self.assertIn((base + 0x3FF0, 1), writes)
            self.assertIn((base + 0x3FF2, 1), writes)
            self.assertEqual(raw[base + 0x3FF5], 0)
            self.assertEqual(
                bytes(v for a, v in writes if a == base + 0x3FF1), b"OEM1,READY\r\n!"
            )
            steps(100)
            self.assertEqual(writes.count((base + 0x3FF0, 1)), 1)
            raw[base + tool.SEQUENCE] = 2
            steps(200)
            self.assertIn((base + 0x3FF2, 2), writes)
            self.assertEqual(cpu.regs.get(RegisterName.S), 0x2000)
            stream = Path(temp) / "stream.bin"
            tool.build_supervisor(root, base, stream, "stream_echo")
            raw[base + 0x400 : base + 0x400 + stream.stat().st_size] = (
                stream.read_bytes()
            )
            cpu.regs.set(RegisterName.PC, base + 0x400)
            incoming.extend(b"A\0\xff")
            writes.clear()
            steps(200)
            self.assertEqual(
                bytes(v for a, v in writes if a == base + 0x3FF1), b"A\0\xff"
            )


if __name__ == "__main__":
    unittest.main()
