#!/usr/bin/env python3
"""Draw the picture that proves the RG35XX Plus panel is alive.

The board has no serial console and the card can only report what software
believes, so whether the display works is settled by a person looking at it.
That needs a picture that cannot be mistaken for noise, a stuck frame or a
half-initialized panel: colour bars that show every channel arrives on the
right lane, a grey ramp that shows the depth is real, a one-pixel border that
shows all four edges land inside the glass, and text that says what drew it.

It is written as a binary PPM because that is what BusyBox's fbsplash reads,
and drawn without an imaging library because the build environment has none.
"""

import argparse
import hashlib
from pathlib import Path

WIDTH, HEIGHT = 640, 480
BARS = (
    (255, 255, 255), (255, 255, 0), (0, 255, 255), (0, 255, 0),
    (255, 0, 255), (255, 0, 0), (0, 0, 255), (0, 0, 0),
)
# Five columns by seven rows, most significant bit on the left.
FONT = {
    " ": (0, 0, 0, 0, 0, 0, 0),
    "-": (0, 0, 0, 0x1F, 0, 0, 0),
    ".": (0, 0, 0, 0, 0, 0x0C, 0x0C),
    ":": (0, 0x0C, 0x0C, 0, 0x0C, 0x0C, 0),
    "/": (0x01, 0x01, 0x02, 0x04, 0x08, 0x10, 0x10),
    "0": (0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E),
    "1": (0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E),
    "2": (0x0E, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1F),
    "3": (0x1F, 0x02, 0x04, 0x02, 0x01, 0x11, 0x0E),
    "4": (0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02),
    "5": (0x1F, 0x10, 0x1E, 0x01, 0x01, 0x11, 0x0E),
    "6": (0x06, 0x08, 0x10, 0x1E, 0x11, 0x11, 0x0E),
    "7": (0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08),
    "8": (0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E),
    "9": (0x0E, 0x11, 0x11, 0x0F, 0x01, 0x02, 0x0C),
    "A": (0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11),
    "B": (0x1E, 0x11, 0x11, 0x1E, 0x11, 0x11, 0x1E),
    "C": (0x0E, 0x11, 0x10, 0x10, 0x10, 0x11, 0x0E),
    "D": (0x1C, 0x12, 0x11, 0x11, 0x11, 0x12, 0x1C),
    "E": (0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F),
    "F": (0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10),
    "G": (0x0E, 0x11, 0x10, 0x17, 0x11, 0x11, 0x0F),
    "H": (0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11),
    "I": (0x0E, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E),
    "J": (0x07, 0x02, 0x02, 0x02, 0x02, 0x12, 0x0C),
    "K": (0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11),
    "L": (0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F),
    "M": (0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11),
    "N": (0x11, 0x11, 0x19, 0x15, 0x13, 0x11, 0x11),
    "O": (0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E),
    "P": (0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10),
    "Q": (0x0E, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0D),
    "R": (0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11),
    "S": (0x0F, 0x10, 0x10, 0x0E, 0x01, 0x01, 0x1E),
    "T": (0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04),
    "U": (0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E),
    "V": (0x11, 0x11, 0x11, 0x11, 0x11, 0x0A, 0x04),
    "W": (0x11, 0x11, 0x11, 0x15, 0x15, 0x15, 0x0A),
    "X": (0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11),
    "Y": (0x11, 0x11, 0x11, 0x0A, 0x04, 0x04, 0x04),
    "Z": (0x1F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F),
}
BARS_END = 264      # colour bars occupy rows [0, BARS_END)
RAMP_END = 312      # the grey ramp occupies rows [BARS_END, RAMP_END)
SCALE = 4           # each font pixel becomes a SCALE x SCALE block
PITCH = 6 * SCALE   # five columns of glyph plus one of space
LINE = 9 * SCALE    # seven rows of glyph plus two of leading


def render(lines: list[str], width: int = WIDTH, height: int = HEIGHT) -> bytes:
    """Return the proof picture as a binary PPM carrying `lines` of text."""
    for line in lines:
        unknown = sorted(set(line.upper()) - set(FONT))
        if unknown:
            raise ValueError(f"no glyph for {unknown!r} in {line!r}")
        if len(line) * PITCH > width - 2 * PITCH:
            raise ValueError(f"{line!r} is too wide for a {width}-pixel panel")
    if RAMP_END + len(lines) * LINE + SCALE > height:
        raise ValueError(f"{len(lines)} lines do not fit under the ramp")

    rows = []
    bar_width = width / len(BARS)
    bar_row = b"".join(bytes(BARS[min(int(x / bar_width), len(BARS) - 1)]) for x in range(width))
    ramp_row = b"".join(bytes([x * 255 // (width - 1)] * 3) for x in range(width))
    black_row = bytes(3 * width)
    for y in range(height):
        rows.append(bytearray(bar_row if y < BARS_END else ramp_row if y < RAMP_END else black_row))

    first = RAMP_END + (height - RAMP_END - len(lines) * LINE) // 2 + SCALE
    for index, line in enumerate(lines):
        left = (width - len(line) * PITCH) // 2
        top = first + index * LINE
        for column, character in enumerate(line.upper()):
            for glyph_row, bits in enumerate(FONT[character]):
                for glyph_column in range(5):
                    if not bits & (0x10 >> glyph_column):
                        continue
                    x0 = left + column * PITCH + glyph_column * SCALE
                    for dy in range(SCALE):
                        row = rows[top + glyph_row * SCALE + dy]
                        row[3 * x0 : 3 * (x0 + SCALE)] = b"\xff" * (3 * SCALE)

    # A white border one pixel wide: if any edge of it is missing, the mode or
    # the panel's porches are wrong even though a picture appears.
    white = b"\xff\xff\xff"
    rows[0][:] = white * width
    rows[-1][:] = white * width
    for row in rows:
        row[0:3] = white
        row[-3:] = white
    return b"P6\n%d %d\n255\n" % (width, height) + b"".join(bytes(row) for row in rows)


def framebuffer_bytes(ppm: bytes) -> bytes:
    """Return the picture as it sits in an XRGB8888 framebuffer.

    That is the format the DRM framebuffer emulation gives /dev/fb0 on this
    board, and BusyBox's fbsplash fills it from the variable screen info: blue
    at bit 0, green at 8, red at 16 and nothing in the top byte, so each pixel
    is the bytes B, G, R, 0 in memory.
    """
    header_end = 0
    for _ in range(3):
        header_end = ppm.index(b"\n", header_end) + 1
    rgb = ppm[header_end:]
    out = bytearray(len(rgb) // 3 * 4)
    out[0::4] = rgb[2::3]
    out[1::4] = rgb[1::3]
    out[2::4] = rgb[0::3]
    return bytes(out)


def framebuffer_md5(lines: list[str]) -> str:
    """The checksum init should report after drawing `lines`, in full.

    Init reads the first 640x480x4 bytes of /dev/fb0 back after fbsplash has
    drawn and reports the first sixteen digits of their MD5, so whether the
    right picture reached the scanout buffer can be checked with nobody there
    to look at the panel.
    """
    return hashlib.md5(framebuffer_bytes(render(lines))).hexdigest()


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--line", action="append", default=[],
                        help="A line of text; repeat for more (A-Z 0-9 space - . : /)")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--expect", action="store_true",
                        help="Print the framebuffer checksum init should report")
    arguments = parser.parse_args(argv)
    lines = arguments.line or ["RG35XX PLUS", "DISPLAY OK"]
    if arguments.expect:
        print(f"fb-md5-{framebuffer_md5(lines)[:16]}")
    if arguments.output is not None:
        arguments.output.write_bytes(render(lines))
        print(f"wrote {arguments.output} ({arguments.output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
