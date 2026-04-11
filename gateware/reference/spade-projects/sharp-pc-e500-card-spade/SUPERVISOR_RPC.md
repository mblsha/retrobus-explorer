# PC-E500 Supervisor RPC

Both host supervisors are expected to expose the same Unix-socket JSON RPC
surface so helper scripts such as
[pc-e500-iocs.py](./scripts/pc-e500-iocs.py) can talk to either one without
implementation-specific branches.

The authoritative machine-readable contract is
[tests/supervisor_rpc_contract.json](./tests/supervisor_rpc_contract.json).

## Transport

- Unix domain socket
- one JSON request per line
- one JSON response per line
- every response includes a top-level `status`

## Common actions

- `status`
  Returns supervisor/device state and recent UART lines.
- `stream_on`
  Sends `F1` and returns the UART reply payload.
- `stream_off`
  Sends `F0` and returns the UART reply payload.
- `stream_status`
  Sends `F?` and returns the UART reply payload.
- `stream_config`
  Programs `FT_STREAM_CFG` and optionally `FT_STREAM_MODE` through a helper
  experiment without consuming the measurement queue.
  Request:
  - `cfg` required integer
  - `mode` optional integer
- `arm_safe`
  Programs the safe supervisor image.
- `debug_echo_short`
  Runs the short echo payload.
  Request:
  - `timeout_s` optional float
- `wait_ready`
  Waits for `XR,READY`.
  Request:
  - `timeout_s` optional float
- `run`
  Runs an experiment helper script.
  Request:
  - `script` required path
  - `script_args` optional string array
- `shutdown`
  Shuts down the daemon.

## Response conventions

- success:
  - `status: "ok"`
- timeout:
  - `status: "timeout"`
  - `needs_reset: true|false`
- request/processing failure:
  - `status: "error"`
  - `error: "<message>"`

Clients should treat the contract above as common across both the Python and
Rust supervisors. Implementation-specific fields may be present, but helpers
should not depend on fields that are not documented here.
