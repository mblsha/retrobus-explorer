"""Direct FT2232H interface B byte stream using libftdi 1.5 or newer."""

import ctypes
import ctypes.util
import math
import runpy
from pathlib import Path
import time


SERIAL_BAUD = runpy.run_path(str(Path(__file__).with_name("uart_config.py")))["SERIAL_BAUD"]


class Context(ctypes.Structure):
    # Public libftdi 1.x context layout. Timeouts and buffered byte count do
    # not have accessor functions; no EEPROM or configuration is written.
    _fields_ = [
        ("usb_ctx", ctypes.c_void_p), ("usb_dev", ctypes.c_void_p),
        ("usb_read_timeout", ctypes.c_int), ("usb_write_timeout", ctypes.c_int),
        ("type", ctypes.c_int), ("baudrate", ctypes.c_int),
        ("bitbang_enabled", ctypes.c_ubyte), ("readbuffer", ctypes.c_void_p),
        ("readbuffer_offset", ctypes.c_uint), ("readbuffer_remaining", ctypes.c_uint),
        ("readbuffer_chunksize", ctypes.c_uint), ("writebuffer_chunksize", ctypes.c_uint),
        ("max_packet_size", ctypes.c_uint), ("interface", ctypes.c_int),
        ("index", ctypes.c_int), ("in_ep", ctypes.c_int), ("out_ep", ctypes.c_int),
        ("bitbang_mode", ctypes.c_ubyte), ("eeprom", ctypes.c_void_p),
        ("error_str", ctypes.c_char_p), ("module_detach_mode", ctypes.c_int),
    ]


class Version(ctypes.Structure):
    _fields_ = [("major", ctypes.c_int), ("minor", ctypes.c_int),
                ("micro", ctypes.c_int), ("version_str", ctypes.c_char_p),
                ("snapshot_str", ctypes.c_char_p)]


def load_library():
    name = ctypes.util.find_library("ftdi1")
    if not name:
        candidate = Path("/opt/homebrew/lib/libftdi1.dylib")
        if candidate.exists():
            name = str(candidate)
    if not name:
        raise RuntimeError("Direct FTDI UART requires libftdi 1.5 or newer")
    return ctypes.CDLL(name)


class FtdiUart:
    """Serial-like I/O on the exact Arty serial number, interface B only.

    Bulk writes are synchronous. The application acknowledgement confirms
    UART drain. Kernel-driver attachment and latency are restored on close.
    """
    def __init__(self, serial_number, baud=SERIAL_BAUD, timeout=0.5):
        if not serial_number or "\0" in serial_number:
            raise ValueError("An exact, nonempty FTDI serial number is required")
        self.lib = load_library()
        self.handle = None
        self.opened = False
        self.timeout = timeout
        self.saved_latency = None
        signatures = {
            "ftdi_new": ([], ctypes.c_void_p),
            "ftdi_free": ([ctypes.c_void_p], None),
            "ftdi_get_library_version": ([], Version),
            "ftdi_get_error_string": ([ctypes.c_void_p], ctypes.c_char_p),
            "ftdi_set_interface": ([ctypes.c_void_p, ctypes.c_int], ctypes.c_int),
            "ftdi_usb_open_desc": ([ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_char_p, ctypes.c_char_p], ctypes.c_int),
            "ftdi_usb_close": ([ctypes.c_void_p], ctypes.c_int),
            "ftdi_setdtr_rts": ([ctypes.c_void_p, ctypes.c_int, ctypes.c_int], ctypes.c_int),
            "ftdi_disable_bitbang": ([ctypes.c_void_p], ctypes.c_int),
            "ftdi_set_line_property2": ([ctypes.c_void_p] + [ctypes.c_int] * 4, ctypes.c_int),
            "ftdi_setflowctrl": ([ctypes.c_void_p, ctypes.c_int], ctypes.c_int),
            "ftdi_set_baudrate": ([ctypes.c_void_p, ctypes.c_int], ctypes.c_int),
            "ftdi_set_latency_timer": ([ctypes.c_void_p, ctypes.c_ubyte], ctypes.c_int),
            "ftdi_get_latency_timer": ([ctypes.c_void_p, ctypes.POINTER(ctypes.c_ubyte)], ctypes.c_int),
            "ftdi_tciflush": ([ctypes.c_void_p], ctypes.c_int),
            "ftdi_read_data": ([ctypes.c_void_p, ctypes.POINTER(ctypes.c_ubyte), ctypes.c_int], ctypes.c_int),
            "ftdi_write_data": ([ctypes.c_void_p, ctypes.POINTER(ctypes.c_ubyte), ctypes.c_int], ctypes.c_int),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(self.lib, name)
            function.argtypes, function.restype = arguments, result
        version = self.lib.ftdi_get_library_version()
        if version.major != 1 or version.minor < 5:
            raise RuntimeError("Unsupported libftdi context ABI; require 1.5 or newer 1.x")
        self.version = version.version_str.decode()
        try:
            self.handle = self.lib.ftdi_new()
            if not self.handle:
                raise RuntimeError("Cannot allocate FTDI context")
            self.context = ctypes.cast(self.handle, ctypes.POINTER(Context)).contents
            self.check("ftdi_set_interface", 2)  # interface B; A remains JTAG
            # Check the public layout before any direct context write.
            self.validate_layout(opened=False)
            self.context.module_detach_mode = 2  # detach and reattach the kernel driver
            self.context.usb_write_timeout = 1000
            self.check("ftdi_usb_open_desc", 0x0403, 0x6010, None, serial_number.encode())
            self.opened = True
            self.validate_layout(opened=True)
            self.check("ftdi_setdtr_rts", 0, 0)
            self.check("ftdi_disable_bitbang")
            self.check("ftdi_set_line_property2", 8, 0, 0, 0)  # 8N1, break off
            self.check("ftdi_setflowctrl", 0)
            self.check("ftdi_set_baudrate", baud)
            latency = ctypes.c_ubyte()
            self.check("ftdi_get_latency_timer", ctypes.byref(latency))
            self.saved_latency = latency.value
            self.check("ftdi_set_latency_timer", 1)
            self.check("ftdi_tciflush")
        except BaseException:
            self.close()
            raise

    def validate_layout(self, *, opened):
        context = self.context
        if (context.interface, context.index, context.in_ep, context.out_ep) != (1, 2, 0x04, 0x83):
            raise RuntimeError("Unsupported libftdi context layout: interface B fields do not match")
        # ftdi_init initializes this final public field to AUTO_DETACH (0).
        # Check it before the direct write too: endpoint fields cannot detect
        # an insertion between them and the tail of the context structure.
        if not opened and context.module_detach_mode != 0:
            raise RuntimeError("Unsupported libftdi context layout: initial module detach mode does not match")
        if opened and (context.type != 4 or context.max_packet_size != 512):
            raise RuntimeError("Unsupported libftdi context layout or device: expected FT2232H with 512-byte packets")

    def check(self, name, *arguments):
        if not self.handle:
            raise OSError("FTDI UART is closed")
        result = getattr(self.lib, name)(self.handle, *arguments)
        if result < 0:
            detail = self.lib.ftdi_get_error_string(self.handle) or b"unknown error"
            raise OSError(f"{name}: {detail.decode(errors='replace')}")
        return result

    @property
    def in_waiting(self):
        if not self.handle:
            raise OSError("FTDI UART is closed")
        return self.context.readbuffer_remaining

    def read(self, size):
        result = bytearray()
        deadline = time.monotonic() + self.timeout
        while len(result) < size:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            self.context.usb_read_timeout = max(1, math.ceil(remaining * 1000))
            buffer = (ctypes.c_ubyte * (size - len(result)))()
            count = self.check("ftdi_read_data", buffer, len(buffer))
            result.extend(bytes(buffer[:count]))
            # USB status-only packets are not a serial timeout. Keep waiting
            # for bytes until the caller's deadline, as pyserial.read does.
        return bytes(result)

    def write(self, data):
        buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        return self.check("ftdi_write_data", buffer, len(data))

    def flush(self):
        pass

    def close(self):
        if self.handle:
            try:
                if self.opened:
                    self.lib.ftdi_setdtr_rts(self.handle, 0, 0)
                    if self.saved_latency is not None:
                        self.lib.ftdi_set_latency_timer(self.handle, self.saved_latency)
                    self.lib.ftdi_usb_close(self.handle)
            finally:
                self.lib.ftdi_free(self.handle)
                self.handle, self.opened = None, False
