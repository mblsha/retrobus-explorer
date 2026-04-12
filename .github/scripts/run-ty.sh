#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/../../py"

uv run ty check \
  --exclude "d3xx/**" \
  --exclude "shared/pyz80/**" \
  --exclude "intel-hex.py" \
  --exclude "sharp-pc-g850.py" \
  --exclude "organizer-misc-signals.py" \
  --exclude "single-bit-png.py" \
  --exclude "perfetto_pb2.py" \
  --exclude "z80bus/server.py" \
  .
