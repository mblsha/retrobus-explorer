"""Shared paths and bitstream round-trip verification for Arty SD builds."""

from pathlib import Path

GATEWARE = Path(__file__).resolve().parents[2]


def verify_frames(output):
    """Compare decoded payload against assembler frames, excluding generated ECC."""
    expected = set()
    for line in (output / "design.frames").read_text().splitlines():
        address, payload = line.split()
        for index, word in enumerate(payload.split(",")):
            value = int(word, 16)
            if index == 50:
                value &= ~0x1FFF  # Series-7 frame ECC, also omitted by bitread.
            while value:
                bit = (value & -value).bit_length() - 1
                expected.add(f"bit_{int(address, 16):08x}_{index:03d}_{bit:02d}")
                value &= value - 1
    actual = set((output / "decoded.bits").read_text().splitlines())
    if not expected or actual != expected:
        raise RuntimeError(
            f"Bitstream round trip failed: {len(expected - actual)} missing, "
            f"{len(actual - expected)} unexpected configuration bits"
        )
    return len(actual)


def begin_build(output):
    """Invalidate success before running any build stage, including preflight."""
    output.mkdir(parents=True, exist_ok=True)
    (output / "result.json").unlink(missing_ok=True)


def publish_result(output, result_text):
    """Publish a complete success manifest atomically after all checks pass."""
    temporary = output / "result.json.tmp"
    try:
        temporary.write_text(result_text)
        temporary.replace(output / "result.json")
    finally:
        temporary.unlink(missing_ok=True)
