pub mod assembler;
pub mod d3xx;
pub mod daemon;
pub mod ft;
pub mod protocol;
pub mod uart;

pub const SUPERVISOR_RPC_ACTIONS: &[&str] = &[
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
];
