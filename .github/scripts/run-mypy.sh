#!/bin/bash
set -e

# Script to run mypy type checking
# Can be used both locally and in CI

# Change to py directory
cd "$(dirname "$0")/../../py"

# Run mypy with the same arguments as in the workflow
mypy --python-version 3.10 \
     --ignore-missing-imports \
     --explicit-package-bases \
     --exclude='(single-bit-png|intel-hex|sharp-pc-g850|organizer-misc-signals|perfetto_pb2|shared/pyz80)\.py$' \
     .