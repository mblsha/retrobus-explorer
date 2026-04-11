# PC-E500 Experiment Daemon (Rust)

Rust port of the host-side continuous experiment supervisor path.

It preserves the existing workflow shape:

- long-lived daemon that owns the Au1 USB-UART
- Unix socket JSON API compatible with the Python `pc-e500-expctl.py` requests
- assembler invocation through the checked-out public assembler
- Python experiment scripts still provide `plan` / `parse`
- continuous FT600 drain thread with per-run cutouts

## Binaries

```sh
cargo run --bin pc-e500-expd-rs -- --arm-safe-on-start --monitor-uart
cargo run --bin pc-e500-expctl-rs -- --pretty status
```

## Notes

- This is meant to replace the Python host daemon, not the calculator-side CE6 supervisor image.
- The wire protocol to the calculator and the experiment scripts are intentionally unchanged.
- FT600 availability rules still apply: if FT600 open fails, stop and restart the FPGA path before continuing hardware experiments.

## Tests

Default coverage:

```sh
cargo test
```

That runs:

- unit tests for protocol parsing, card-ROM image building, and FT word decode/classification
- socket-level integration tests for `pc-e500-expctl-rs` request/response behavior

Opt-in hardware smoke tests are present but skipped unless explicitly enabled:

```sh
PC_E500_HW=1 cargo test --test hardware_smoke daemon_status_smoke_opt_in -- --nocapture

# Requires the calculator to already be at XR,READY,01,SAFEFT
PC_E500_HW_FULL=1 cargo test --test hardware_smoke daemon_ready_and_run_smoke_opt_in -- --nocapture
```

Optional environment:

- `PC_E500_SERIAL_PORT=/dev/cu.usbserial-...` to force the Au1 port instead of auto-detect
