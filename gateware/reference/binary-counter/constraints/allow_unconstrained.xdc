# Allow non-board-specific builds by downgrading unconstrained I/O checks.
# This is useful for CI/remote synth runs where exact board pin maps are unknown.
set_property SEVERITY Warning [get_drc_checks UCIO-1]
set_property SEVERITY Warning [get_drc_checks NSTD-1]
