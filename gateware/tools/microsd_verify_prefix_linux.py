#!/usr/bin/env python3
"""Modify a bounded UART-uploaded prefix on the verified external FPGA SD card."""
import hashlib
import json
import mmap
import os
from microsd_verify_linux_rw import validate_target


def image_prefix():
    return bytes((i * 37 + (i >> 8) * 11 + 17) & 255 for i in range(65536))


def main():
    validate_target(4, 256 << 20, 13_000_000, 12_913_043)
    original = image_prefix()
    expected = bytearray(original)
    expected[4096:8192] = bytes(byte ^ 0xa5 for byte in expected[4096:8192])
    fd = os.open('/dev/mmcblk1', os.O_RDWR | os.O_DIRECT)
    checks = []
    try:
        def read(offset, size):
            with mmap.mmap(-1, size) as buffer:
                assert os.preadv(fd, [buffer], offset) == size
                return bytes(buffer)
        assert read(0, len(original)) == original
        for offset in (65536, (256 << 20) - 4096):
            assert read(offset, 4096) == bytes(4096)
        with mmap.mmap(-1, 4096) as buffer:
            buffer[:] = expected[4096:8192]
            assert os.pwritev(fd, [buffer], 4096) == 4096
        os.fsync(fd)
        for _ in range(3):
            actual = read(0, len(expected))
            assert actual == expected
            checks.append(hashlib.sha256(actual).hexdigest())
        for offset in (65536, (256 << 20) - 4096):
            assert read(offset, 4096) == bytes(4096)
    finally:
        os.close(fd)
    validate_target(4, 256 << 20, 13_000_000, 12_913_043)
    print(json.dumps({'verified_prefix_bytes':len(original),'modified_offset':4096,
                      'modified_bytes':4096,'before_sha256':hashlib.sha256(original).hexdigest(),
                      'after_sha256':hashlib.sha256(expected).hexdigest(),
                      'readback_sha256':checks,'untouched_tail_and_last_page_zero':True},indent=2))


if __name__ == '__main__':
    main()
