from __future__ import annotations


SUPERVISOR_RPC_ACTIONS: tuple[str, ...] = (
    "status",
    "stream_on",
    "stream_off",
    "stream_status",
    "stream_config",
    "arm_safe",
    "debug_echo_short",
    "wait_ready",
    "run",
    "shutdown",
)
