#!/bin/bash
set -e

# GitHub Actions script to run Alchitry tests using the shared core logic
# This script sources the same test-core.sh used by local container testing

# Get the script directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Source the core testing functions
source "$SCRIPT_DIR/../container/test-core.sh"

# Get project from argument
PROJECT="$1"

if [ -z "$PROJECT" ]; then
    echo "❌ Error: Project name required as first argument"
    exit 1
fi

# Ensure ALCHITRY_BIN is set
if [ -z "$ALCHITRY_BIN" ]; then
    echo "❌ Error: ALCHITRY_BIN environment variable not set"
    exit 1
fi

echo "🧪 Testing project: $PROJECT"
echo "📍 Using Alchitry binary: $ALCHITRY_BIN"

# Get the project directory
PROJECT_DIR="$(cd "$SCRIPT_DIR/../../gateware/$PROJECT" && pwd)"

if [ ! -d "$PROJECT_DIR" ]; then
    echo "❌ Error: Project directory not found: $PROJECT_DIR"
    exit 1
fi

# Run the test
if check_project "$PROJECT" "$PROJECT_DIR" "$ALCHITRY_BIN"; then
    echo "✅ Project $PROJECT passed all checks!"
    exit 0
else
    echo "❌ Project $PROJECT failed checks"
    exit 1
fi