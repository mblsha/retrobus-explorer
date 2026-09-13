#!/usr/bin/env python3
"""Safely detach the GKD external MMC controller before FPGA programming/upload."""

from microsd_host import prepare_for_programming


def main():
    print(prepare_for_programming())


if __name__ == "__main__":
    main()
