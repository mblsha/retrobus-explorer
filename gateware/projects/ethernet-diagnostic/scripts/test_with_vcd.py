#!/usr/bin/env python3
"""Run Ethernet/SD simulations, preserving individual results."""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--waves", action="store_true", help="Retain simulation waveforms"
    )
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    runner = project.parents[1] / "tools/run_tb.py"
    for top, module in [
        ("frame_receiver", "test_mac"),
        ("frame_transmitter", "test_mac"),
        ("network_engine", "test_network"),
        ("block_service", "test_blocks"),
        ("network_native", "test_network_native"),
        ("network_ddr", "test_network_sd"),
    ]:
        subprocess.run(
            [
                sys.executable,
                str(runner),
                "--project",
                str(project),
                "--top",
                top,
                "--test-module",
                module,
                *(["--waves"] if args.waves else []),
            ],
            check=True,
        )
        shutil.copyfile(
            project / "test/results.xml", project / f"test/{top}.results.xml"
        )


if __name__ == "__main__":
    main()
