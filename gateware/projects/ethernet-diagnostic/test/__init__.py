"""Cocotb testbenches and the wire-format helpers they share.

The helpers are also read by the host tests in `test_host`, which run with
`projects/ethernet-diagnostic` as their top-level directory, so this package
marker is what lets them import the protocol scenarios rather than keep a
second copy of them.

Naming it `test` shadows the standard library's own `test` package, but only
while `projects/ethernet-diagnostic` is on the path, which is only during a
host-test discovery run. Nothing in this tree imports stdlib `test`, and the
Cocotb runs start with `test/` as their working directory and so never see the
directory above it at all. Renaming it would move the testbenches `run_tb.py`
discovers, which is a larger change than the shadow is worth.
"""
