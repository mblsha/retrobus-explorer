#!/bin/bash
set -e

# Test script for Alchitry CI container
# This script runs the same checks as GitHub Actions but locally

echo "🧪 Testing Alchitry CI container locally..."

# Get the script directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Source the core testing functions
source "$SCRIPT_DIR/test-core.sh"

# Get the project root (two levels up from this script)
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Default to all projects unless specific ones are provided
if [ $# -eq 0 ]; then
    PROJECTS=(
        "test-minimal"
        "pin-tester"
        "sharp-organizer-card"
        "sharp-pc-g850-bus"
        "sharp-pc-g850-streaming-rom"
    )
else
    PROJECTS=("$@")
fi

echo "📋 Testing projects: ${PROJECTS[*]}"

# Detect container runtime (Docker or Apple container)
if command -v docker &> /dev/null; then
    CONTAINER_CMD="docker"
elif command -v container &> /dev/null; then
    CONTAINER_CMD="container"
else
    echo "❌ No container runtime found (docker or container)"
    exit 1
fi

# Function to run checks for a single project in container
check_project_container() {
    local project=$1
    
    $CONTAINER_CMD run --rm \
        --volume "$PROJECT_ROOT:/workspace" \
        --volume "$SCRIPT_DIR:/scripts:ro" \
        retrobus-alchitry-ci \
        bash -c "
            source /scripts/test-core.sh
            check_project '$project' '/workspace/gateware/$project' '\$ALCHITRY_BIN'
        "
    
    return $?
}

# Track results
FAILED_PROJECTS=()
PASSED_PROJECTS=()

# Run checks for each project
for project in "${PROJECTS[@]}"; do
    if check_project_container "$project"; then
        PASSED_PROJECTS+=("$project")
    else
        FAILED_PROJECTS+=("$project")
    fi
done

# Display summary using the core function
display_summary "${PASSED_PROJECTS[*]}" "${FAILED_PROJECTS[*]}"
exit $?