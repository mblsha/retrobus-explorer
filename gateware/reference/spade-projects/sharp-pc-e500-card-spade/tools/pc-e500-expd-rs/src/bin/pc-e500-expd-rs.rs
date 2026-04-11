use std::path::PathBuf;

use anyhow::Result;
use pc_e500_expd_rs::daemon::{serve, ExperimentDaemon};
use pc_e500_expd_rs::protocol::{
    default_assembler_dir, default_safe_asm, default_socket_path, DEFAULT_BAUD, DEFAULT_IDLE_GAP_S,
    DEFAULT_QUIET_TIMEOUT_S,
};

fn main() -> Result<()> {
    let mut socket = default_socket_path();
    let mut port = None;
    let mut baud = DEFAULT_BAUD;
    let mut idle_gap = DEFAULT_IDLE_GAP_S;
    let mut quiet_timeout = DEFAULT_QUIET_TIMEOUT_S;
    let mut assembler_dir = default_assembler_dir();
    let mut safe_asm = default_safe_asm();
    let mut arm_safe_on_start = false;
    let mut monitor_uart = false;
    let mut enable_ft = true;

    let mut args = std::env::args().skip(1);
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--socket" => socket = PathBuf::from(args.next().expect("missing --socket value")),
            "--port" => port = Some(args.next().expect("missing --port value")),
            "--baud" => baud = args.next().expect("missing --baud value").parse()?,
            "--idle-gap" => idle_gap = args.next().expect("missing --idle-gap value").parse()?,
            "--quiet-timeout" => {
                quiet_timeout = args
                    .next()
                    .expect("missing --quiet-timeout value")
                    .parse()?
            }
            "--assembler-dir" => {
                assembler_dir = PathBuf::from(args.next().expect("missing --assembler-dir value"))
            }
            "--safe-asm" => {
                safe_asm = PathBuf::from(args.next().expect("missing --safe-asm value"))
            }
            "--arm-safe-on-start" => arm_safe_on_start = true,
            "--monitor-uart" => monitor_uart = true,
            "--no-ft" => enable_ft = false,
            other => anyhow::bail!("unknown argument: {other}"),
        }
    }

    let mut daemon = ExperimentDaemon::new(
        port,
        baud,
        idle_gap,
        quiet_timeout,
        assembler_dir,
        safe_asm,
        monitor_uart,
        enable_ft,
    )?;
    if arm_safe_on_start {
        daemon.program_safe_image()?;
    }
    let result = serve(&socket, &mut daemon)?;
    daemon.close();
    std::process::exit(result);
}
