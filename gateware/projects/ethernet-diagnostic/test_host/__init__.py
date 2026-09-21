"""Host-side unit tests for the ethernet diagnostic's Python tooling.

They are a package so that `projects/ethernet-diagnostic` can be the top-level
directory of a discovery run, which is what makes `scripts` importable the same
way the shipped entry points import it. The Cocotb testbenches stay in `test/`
and are run by `tools/run_tb.py`.
"""
