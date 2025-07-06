#!/bin/bash
# FuseSoC build wrapper for pin-tester project

set -e

echo "=== RetroBus Pin Tester FuseSoC Build ==="

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Simply call the generic build script with pin-tester as the project
exec "$SCRIPT_DIR/build_local.sh" pin-tester "$@"