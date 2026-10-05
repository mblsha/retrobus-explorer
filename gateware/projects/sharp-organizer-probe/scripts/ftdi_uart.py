"""Reuse the repository's checked direct FT2232H UART implementation."""

from functools import lru_cache
from pathlib import Path
import runpy


def parse_uart_uri(uri: str) -> str:
    if not uri.startswith("ftdi://"):
        raise ValueError("direct FTDI UART URI must be ftdi://SERIAL/B")
    serial, separator, interface = uri[len("ftdi://"):].partition("/")
    if not serial.isascii() or not serial.isalnum() or separator != "/" or interface != "B":
        raise ValueError("specify an FTDI serial and UART interface B: ftdi://SERIAL/B")
    return serial


@lru_cache(maxsize=1)
def _implementation():
    source = Path(__file__).resolve().parents[2] / "ethernet-diagnostic/scripts/ftdi_uart.py"
    return runpy.run_path(str(source))["FtdiUart"]


def open_ftdi_uart(uri: str, baud: int):
    serial = parse_uart_uri(uri)
    return _Port(_implementation()(serial, baud=baud, timeout=0.5), uri, baud)


class _Port:
    def __init__(self, backend, uri, baud):
        self._backend = backend
        self.baudrate = baud
        self.transport = "libftdi1"
        self.port = uri

    def __getattr__(self, name):
        return getattr(self._backend, name)

    def reset_input_buffer(self):
        self._backend.check("ftdi_tciflush")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._backend.close()
