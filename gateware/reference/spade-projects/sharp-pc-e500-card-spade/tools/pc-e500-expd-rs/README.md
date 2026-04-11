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

