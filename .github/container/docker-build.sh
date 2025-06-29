#!/bin/bash
set -e

echo "Building Alchitry CI container with Docker..."

# Build from the container directory, using parent directory as context
cd "$(dirname "$0")"
docker build -t retrobus-alchitry-ci -f Dockerfile ..

echo "Build complete! Run with:"
echo "  docker run --rm -it --volume \"\$(pwd):/workspace\" retrobus-alchitry-ci"