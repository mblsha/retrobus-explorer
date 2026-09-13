"""Independent wire-format builders; do not use the production encoder here."""

import struct
import zlib


def packet(op, seq, lba=0, count=0, data=b"", session=0x12345678):
    body = (
        b"RBS1"
        + bytes([op, 0, 0, 0])
        + struct.pack("<IIII", session, seq, lba, count)
        + data.ljust(512, b"\0")
    )
    assert len(body) == 536
    return body + struct.pack("<I", zlib.crc32(body))


MAC = bytes.fromhex("020000000001")
HOST = bytes.fromhex("9c69d380dc49")
IP = bytes([192, 168, 10, 2])
HOST_IP = bytes([192, 168, 10, 1])


def checksum(data):
    data += b"\0" * (len(data) % 2)
    value = sum(struct.unpack("!%dH" % (len(data) // 2), data))
    while value >> 16:
        value = (value & 65535) + (value >> 16)
    return value ^ 65535


def ipv4(protocol, payload, destination=IP, fragment=0):
    header = struct.pack(
        "!BBHHHBBH4s4s",
        0x45,
        0,
        20 + len(payload),
        13,
        fragment,
        64,
        protocol,
        0,
        HOST_IP,
        destination,
    )
    header = header[:10] + struct.pack("!H", checksum(header)) + header[12:]
    return (MAC + HOST + b"\x08\x00" + header + payload).ljust(60, b"\0")


def udp(payload, checked=True):
    length = 8 + len(payload)
    header = struct.pack("!HHHH", 23456, 4000, length, 0)
    if checked:
        value = (
            checksum(
                HOST_IP
                + IP
                + bytes([0, 17])
                + struct.pack("!H", length)
                + header
                + payload
            )
            or 65535
        )
        header = header[:6] + struct.pack("!H", value)
    return ipv4(17, header + payload)
