"""Read and change one cell of a flattened device tree, in place.

The card image carries the device tree U-Boot hands to Linux, and the one thing
a build needs to change in it is a number that is already there: the fastest
clock Linux may give the emulated card. Changing a cell in place needs no
compiler and cannot move anything else in the blob, so that is all this does.
"""

from __future__ import annotations

import struct

FDT_MAGIC = 0xD00DFEED
_BEGIN_NODE, _END_NODE, _PROP, _NOP, _END = 1, 2, 3, 4, 9

# The controller the emulated card sits on: SD slot 1 of the RG35XX Plus.
CARD_CONTROLLER = "/soc/mmc@4020000"
CARD_CLOCK_PROPERTY = "max-frequency"


def _aligned(offset: int) -> int:
    return (offset + 3) & ~3


def _cell_offset(blob: bytes, node: str, name: str) -> int:
    """Return the offset of a one-cell property's value within the blob."""
    magic, _, structure, strings = struct.unpack_from(">4I", blob, 0)
    if magic != FDT_MAGIC:
        raise ValueError("not a flattened device tree")
    wanted = [part for part in node.split("/") if part]
    path: list[str] = []
    offset = structure
    while True:
        (token,) = struct.unpack_from(">I", blob, offset)
        offset += 4
        if token == _BEGIN_NODE:
            end = blob.index(b"\0", offset)
            label = blob[offset:end].decode()
            if label or path:
                path.append(label)
            offset = _aligned(end + 1)
        elif token == _END_NODE:
            if path:
                path.pop()
        elif token == _PROP:
            length, name_offset = struct.unpack_from(">2I", blob, offset)
            offset += 8
            end = blob.index(b"\0", strings + name_offset)
            if path == wanted and blob[strings + name_offset:end].decode() == name:
                if length != 4:
                    raise ValueError(f"{node}:{name} is {length} bytes, not one cell")
                return offset
            offset = _aligned(offset + length)
        elif token == _NOP:
            continue
        elif token == _END:
            raise ValueError(f"the device tree has no {node}:{name}")
        else:
            raise ValueError(f"unknown device tree token {token:#x}")


def get_cell(blob: bytes, node: str, name: str) -> int:
    return struct.unpack_from(">I", blob, _cell_offset(blob, node, name))[0]


def set_cell(blob: bytes, node: str, name: str, value: int) -> bytes:
    """Return the blob with one existing cell changed and nothing else moved."""
    offset = _cell_offset(blob, node, name)
    changed = bytearray(blob)
    struct.pack_into(">I", changed, offset, value)
    return bytes(changed)
