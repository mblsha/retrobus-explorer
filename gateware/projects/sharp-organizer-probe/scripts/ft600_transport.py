"""FT600 burst payloads using the repository's D3XX bindings."""

from __future__ import annotations

import sys
import time
from pathlib import Path


def decode_payload(raw: bytes, count: int) -> bytes:
    if len(raw) != count * 2:
        raise OSError(f"FT600 payload ended after {len(raw)}/{count * 2} bytes; capture aborted")
    if raw[1::2] != b"\xa5" * count:
        index = next(index for index, marker in enumerate(raw[1::2]) if marker != 0xa5)
        raise OSError(f"FT600 0xa5 word marker mismatch at word {index}; capture aborted")
    return raw[::2]


class Ft600:
    def __init__(self, serial: str):
        if not serial or "\0" in serial:
            raise ValueError("an exact FT600 serial number is required")
        bindings = Path(__file__).resolve().parents[4] / "py/d3xx"
        if str(bindings) not in sys.path:
            sys.path.insert(0, str(bindings))
        import ftd3xx
        from defines import FT_OK, FT_TIMEOUT, FT_OPEN_BY_SERIAL_NUMBER

        self.serial = serial
        self._valid_status = (FT_OK, FT_TIMEOUT)
        devices = [ftd3xx.getDeviceInfoDetail(index)
                   for index in range(ftd3xx.createDeviceInfoList())]
        matches = [device for device in devices if device["SerialNumber"].decode() == serial]
        if len(matches) != 1 or matches[0]["Type"] not in (600, 601):
            raise OSError("need exactly one FT600/601 device with the requested serial")
        self.info = matches[0]
        self.dev = ftd3xx.create(serial.encode(), FT_OPEN_BY_SERIAL_NUMBER)
        if self.dev is None:
            raise OSError(f"cannot open FT600 serial {serial!r}")
        try:
            configuration = self.dev.getChipConfiguration()
            if self.dev.status != FT_OK or (configuration.FIFOMode, configuration.ChannelConfig) != (0, 2):
                raise OSError("FT600 must already use FT245 FIFO mode and one bidirectional channel")
            self.configuration = {name: getattr(configuration, name)
                                  for name in ("FIFOClock", "FIFOMode", "ChannelConfig")}
        except Exception:
            self.close()
            raise

    def read(self, size: int, timeout_ms: int = 20) -> bytes:
        result = self.dev.readPipeEx(0, size, timeout=timeout_ms, raw=True)
        if self.dev.status not in self._valid_status:
            raise OSError(f"FT600 USB read failed with D3XX status {self.dev.status}")
        return result["bytes"]

    def drain(self) -> None:
        # Called only after a verified UART park: no new card data is queued.
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            if not self.read(65536):
                return
        raise OSError("FT600 did not become idle after parking; capture aborted")

    def read_payload(self, count: int, phase_ns: int) -> bytes:
        size = count * 2
        result = bytearray()
        deadline = time.monotonic() + max(1, count * phase_ns * 2 / 1e9 + 1)
        while len(result) < size and time.monotonic() < deadline:
            result.extend(self.read(size - len(result)))
        # Do not retry FT600 timeouts: queued FIFO bytes would need a new
        # verified park and drain before they could be attributed to a read.
        return decode_payload(bytes(result), count)

    def close(self) -> None:
        if self.dev is not None:
            self.dev.close()
            self.dev = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
