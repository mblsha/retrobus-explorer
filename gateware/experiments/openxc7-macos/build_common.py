"""Shared paths and bitstream round-trip verification for Arty SD builds."""

from pathlib import Path
import subprocess

GATEWARE = Path(__file__).resolve().parents[2]
DEFAULT_TOOLCHAIN = GATEWARE / "build/openxc7-macos"


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


def pack_and_verify_bitstream(toolchain, output, *, env=None):
    """Package this Arty's routed FASM and verify the decoded configuration bits."""
    toolchain, output = Path(toolchain).resolve(), Path(output).resolve()
    part = "xc7a35tcsg324-1"
    db = toolchain / "share/prjxray/artix7"
    part_file = str(db / part / "part.yaml")
    steps = [
        (
            "frames",
            [
                str(toolchain / "venv/bin/python"),
                str(toolchain / "libexec/fasm2frames.py"),
                "--db-root",
                str(db),
                "--part",
                part,
                "design.fasm",
            ],
        ),
        (
            "bitstream",
            [
                str(toolchain / "bin/xc7frames2bit"),
                "--part_file",
                part_file,
                "--part_name",
                part,
                "--frm_file",
                "design.frames",
                "--output_file",
                "design.bit",
            ],
        ),
        (
            "decode",
            [
                str(toolchain / "bin/bitread"),
                "--part_file",
                part_file,
                "-y",
                "-z",
                "-o",
                "decoded.bits",
                "design.bit",
            ],
        ),
    ]
    for stage, command in steps:
        print(stage, flush=True)
        with (output / f"{stage}.log").open("w") as log:
            if stage == "frames":
                with (output / "design.frames").open("w") as frames:
                    subprocess.run(
                        command,
                        cwd=output,
                        env=env,
                        stdout=frames,
                        stderr=log,
                        check=True,
                    )
            else:
                subprocess.run(
                    command, cwd=output, env=env, stdout=log, stderr=log, check=True
                )
    return verify_frames(output)
