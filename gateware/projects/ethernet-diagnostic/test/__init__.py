"""Cocotb testbenches and the wire-format helpers they share.

The helpers are also read by the host tests in `test_host`, which run with
`projects/ethernet-diagnostic` as their top-level directory, so this package
marker is what lets them import the protocol scenarios rather than keep a
second copy of them.
"""
