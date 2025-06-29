#!/bin/bash
set -e

echo "Building Alchitry CI container..."

# Build from the container directory, using parent directory as context
cd "$(dirname "$0")"
container build -t retrobus-alchitry-ci -f Dockerfile ..

echo "Build complete! Run with:"
echo "  container run --rm -it --volume \"\$(pwd):/workspace\" retrobus-alchitry-ci"