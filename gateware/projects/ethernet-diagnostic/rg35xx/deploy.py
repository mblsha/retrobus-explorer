#!/usr/bin/env python3
"""Put one verified image on the bench: program, upload, verify, arm.

These four steps were a shell script on the bench, which is why two runs were
made against a bitstream nobody recorded and one against an image that had
never been verified. Each step here refuses to start unless the step before it
can be shown to have happened: the target must be powered off before the FPGA
is reprogrammed, the image must satisfy the boot contract before it is
programmed, and the sha the card reports back must be the sha of the file.

Nothing here powers the target on. A trial does that, and it disarms the card
afterwards; this only leaves a card armed with a known image.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path

from rg35xx.image import verify_boot_image
from scripts import images

DEFAULT_CHANNEL = "psu2"
# psu1 powers the Zaurus on this bench. A card deploy that switched it would
# cut power to an unrelated machine, so the name is refused outright rather
# than guarded by a prompt.
FORBIDDEN_CHANNELS = ("psu1",)
BOARD = "arty_a7_35t"
# The FPGA reloads its DDR controller after programming; uploading into it
# before that is how a verified upload came back with the wrong readback.
PROGRAM_SETTLE_SECONDS = 8
# Windowed readback verifies the upload with independent tokens, so a lost
# reply costs one window rather than the whole image.
UPLOAD_WINDOW = 10
OUTPUT_STATE = re.compile(r"^\s*Output:\s*(\S+)\s*$", re.MULTILINE)
ONLINE_STATE = re.compile(r"^\s*Online:\s*(\S+)\s*$", re.MULTILINE)


def checked_channel(channel: str) -> str:
    if channel in FORBIDDEN_CHANNELS:
        raise ValueError(
            f"{channel} powers another device on this bench and must not be "
            "switched by a card deploy"
        )
    return channel


def output_is_off(status: str) -> bool:
    """Read the output state out of one `--status` report.

    A status that names no output state, or more than one, is not evidence
    that the target is off, so it is an error rather than a false.
    """
    states = OUTPUT_STATE.findall(status)
    if len(states) != 1:
        raise ValueError("PSU status does not report exactly one output state")
    return states[0].upper() == "OFF"


def supply_is_online(status: str) -> bool:
    """Whether the module behind this channel is actually reporting.

    The supply modules reach the controller over a wireless link that drops.
    While it is down the CLI still prints a status, all zeroes with the output
    shown OFF, which is what it knows and not what is true: the module may be
    powering the target at that moment. A status that does not say the module
    is online is therefore evidence of nothing.
    """
    states = ONLINE_STATE.findall(status)
    if len(states) != 1:
        raise ValueError("PSU status does not report exactly one online state")
    return states[0].upper() == "YES"


def psu_status(cli: Path, channel: str) -> str:
    result = subprocess.run(
        ["npm", "run", "start", "--silent", "--", checked_channel(channel), "--status"],
        cwd=cli, capture_output=True, text=True, timeout=120, check=False,
    )
    if result.returncode:
        raise RuntimeError(f"{channel} status failed: {result.stderr.strip()}")
    return result.stdout


def require_target_off(cli: Path, channel: str) -> None:
    """Refuse to reprogram the FPGA while the target is drawing from the card.

    The card disappears for several seconds while the bitstream loads. A target
    powered through that sees an I/O error rather than a slow card, and the
    boot it then attempts is not the boot under test.
    """
    status = psu_status(cli, channel)
    if not supply_is_online(status):
        raise RuntimeError(
            f"{channel} is offline, so whether the target is powered is unknown; "
            "bring the supply module back before deploying"
        )
    if not output_is_off(status):
        raise RuntimeError(f"{channel} output is ON; power the target off first")


def manifest_summary(build_dir: Path) -> list[str]:
    """Say which bitstream this is, in the terms a note would cite it by."""
    manifest = json.loads((build_dir / "result.json").read_text())
    clocks = {
        name: value[0] if isinstance(value, list) else value
        for name, value in manifest.get("clocks_mhz", {}).items()
    }
    return [
        f"bitstream {manifest.get('bitstream_sha256')}",
        f"seed {manifest.get('placement_seed')} "
        f"bits {manifest.get('verified_configuration_bits')}",
        f"clocks {clocks}",
        f"h700 {manifest.get('h700_mmc')} "
        f"early_command {manifest.get('h700_early_command')}",
    ]


def program(build_dir: Path) -> None:
    subprocess.run(
        ["openFPGALoader", "-b", BOARD, "-m", str(build_dir / "design.bit")],
        check=True,
    )


def clear_session(state: Path) -> None:
    """Drop the journal, because the session it describes died with the FPGA."""
    for path in (state, state.with_name(state.name + ".lock")):
        path.unlink(missing_ok=True)


def upload_and_verify(client, image: Path) -> str:
    """Upload the image and confirm the card holds exactly these bytes."""
    payload = image.read_bytes()
    expected = hashlib.sha256(payload).hexdigest()
    client.upload(payload, window=UPLOAD_WINDOW)
    recorded = (client.initial_upload or {}).get("sha256")
    if recorded != expected:
        raise RuntimeError(
            f"card verified {recorded}, image is {expected}"
        )
    if not (client.initial_upload or {}).get("verified"):
        raise RuntimeError("upload readback was not verified")
    return expected


def armed_summary(client) -> str:
    trace = client.trace()
    status = trace["protocol_status"]
    return (
        f"armed {trace['armed']} ddr {trace['ddr_initialized']} "
        f"edges {trace['clock_edges']} frames {trace['command_frames']} "
        f"idle_data_high {status.get('idle_data_high')}"
    )


def deploy(build_dir: Path, image: Path, state: Path, psu_cli: Path,
           channel: str, client_factory=None) -> str:
    # The image is checked before anything is switched or programmed: an image
    # that cannot boot is not worth a bench cycle, and finding out after the
    # FPGA is loaded means doing the whole sequence again.
    verify_boot_image(image)
    require_target_off(psu_cli, checked_channel(channel))
    for line in manifest_summary(build_dir):
        print(line)
    program(build_dir)
    time.sleep(PROGRAM_SETTLE_SECONDS)
    clear_session(state)
    factory = client_factory or (lambda: images.Images(state=str(state)))
    client = factory()
    try:
        digest = upload_and_verify(client, image)
        print(f"uploaded and verified {digest}")
        client.command(images.Opcode.ARM)
        print(armed_summary(client))
    finally:
        client.close()
    return digest


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, required=True,
                        help="Build directory holding design.bit and result.json")
    parser.add_argument("--image", type=Path, required=True,
                        help="Card image to serve; it must pass --verify-image")
    parser.add_argument("--state", type=Path, required=True,
                        help="images.py session file")
    parser.add_argument(
        "--psu-cli", type=Path, default=os.environ.get("MDP_CLI"),
        help="Miniware MDP CLI checkout (default: $MDP_CLI)",
    )
    parser.add_argument(
        "--channel", default=DEFAULT_CHANNEL,
        help="PSU channel powering the target; it must already be off",
    )
    arguments = parser.parse_args(argv)
    if arguments.psu_cli is None:
        parser.error("--psu-cli or $MDP_CLI is required to read the target's power")
    try:
        deploy(
            arguments.build_dir, arguments.image, arguments.state,
            arguments.psu_cli, arguments.channel,
        )
    except (ValueError, RuntimeError) as failure:
        raise SystemExit(str(failure))


if __name__ == "__main__":
    main()
