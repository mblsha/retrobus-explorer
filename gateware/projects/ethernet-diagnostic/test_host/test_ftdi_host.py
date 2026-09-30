import ctypes
import os
import unittest
from unittest.mock import patch

from scripts import ftdi_uart, images
from test_host.test_images_host import ProtocolPeer


class Function:
    def __init__(self, library, name):
        self.library, self.name = library, name

    def __call__(self, *args):
        return self.library.call(self.name, args)


class Library:
    def __init__(self, data=b"", fail=None):
        self.context = ftdi_uart.Context()
        self.calls = []
        self.functions = {}
        self.data = bytearray(data)
        self.empty_reads = 2
        self.fail = fail

    def __getattr__(self, name):
        if name not in self.functions:
            self.functions[name] = Function(self, name)
        return self.functions[name]

    def call(self, name, args):
        self.calls.append((name, args))
        if name == self.fail:
            return -1
        if name == "ftdi_get_library_version":
            return ftdi_uart.Version(1, 5, 0, b"1.5", b"")
        if name == "ftdi_new":
            return ctypes.addressof(self.context)
        if name == "ftdi_get_error_string":
            return b"injected USB configuration failure"
        if name == "ftdi_get_latency_timer":
            ctypes.cast(args[1], ctypes.POINTER(ctypes.c_ubyte)).contents.value = 16
        if name == "ftdi_read_data":
            if self.empty_reads:
                self.empty_reads -= 1
                return 0
            count = min(args[2], len(self.data))
            for index in range(count):
                args[1][index] = self.data[index]
            del self.data[:count]
            self.context.readbuffer_remaining = len(self.data)
            return count
        if name == "ftdi_write_data":
            return args[2]
        return 0


class FtdiTests(unittest.TestCase):
    def test_exact_board_interface_inactive_lines_and_status_only_packets(self):
        library = Library(b"\0\xff\0A")
        with patch.object(ftdi_uart, "load_library", return_value=library):
            port = ftdi_uart.FtdiUart("exact-board")
            self.assertEqual(library.context.module_detach_mode, 2)
            self.assertEqual(port.read(4), b"\0\xff\0A")
            self.assertEqual(port.write(b"\0\xff"), 2)
            port.close()
            port.close()
        calls = library.calls
        self.assertIn(("ftdi_set_interface", (ctypes.addressof(library.context), 2)), calls)
        self.assertIn(("ftdi_usb_open_desc", (ctypes.addressof(library.context), 0x0403, 0x6010, None, b"exact-board")), calls)
        modem = [args[1:] for name, args in calls if name == "ftdi_setdtr_rts"]
        self.assertEqual(modem, [(0, 0), (0, 0)])
        latency = [args[1] for name, args in calls if name == "ftdi_set_latency_timer"]
        self.assertEqual(latency, [1, 16])
        self.assertEqual(sum(name == "ftdi_usb_close" for name, _ in calls), 1)
        self.assertEqual(sum(name == "ftdi_free" for name, _ in calls), 1)
        with self.assertRaises(OSError):
            port.read(1)

    def test_failed_configuration_releases_the_claimed_interface(self):
        library = Library(fail="ftdi_set_baudrate")
        with patch.object(ftdi_uart, "load_library", return_value=library):
            with self.assertRaisesRegex(OSError, "configuration failure"):
                ftdi_uart.FtdiUart("exact-board")
        self.assertIn("ftdi_usb_close", [name for name, _ in library.calls])
        self.assertIn("ftdi_free", [name for name, _ in library.calls])

    def test_invalid_selector_never_opens_usb(self):
        with patch.object(ftdi_uart, "load_library") as load:
            for selector in ("", "board\0suffix"):
                with self.assertRaises(ValueError):
                    ftdi_uart.FtdiUart(selector)
            load.assert_not_called()

    def test_backend_selection_and_explicit_tty_override(self):
        peer = ProtocolPeer()
        with patch.dict(os.environ, SD_EMULATOR_FTDI_SERIAL="exact-board", SD_EMULATOR_SERIAL_PORT="tty"):
            with patch.object(images, "SerialTransport", return_value=peer) as transport:
                client = images.Images()
                client.close()
                self.assertEqual(transport.call_args.kwargs["ftdi_serial"], "exact-board")
                client = images.Images(serial_port="explicit-tty")
                client.close()
                self.assertEqual(transport.call_args.args[0], "explicit-tty")
        with self.assertRaises(ValueError):
            images.Images(serial_port="tty", ftdi_serial="board")

    def test_explicit_invalid_selector_never_falls_back_to_udp(self):
        with patch.object(images.socket, "socket") as udp:
            with patch.object(images, "SerialTransport") as uart:
                for value in ("", "board\0suffix"):
                    for key in ("serial_port", "ftdi_serial"):
                        with self.subTest(key=key, value=value):
                            with self.assertRaises(ValueError):
                                images.Images(**{key: value})
                udp.assert_not_called()
                uart.assert_not_called()
