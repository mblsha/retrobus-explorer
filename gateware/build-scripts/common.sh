#!/bin/bash
# Common functions for build scripts
# Source this file in other scripts: source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

# Import project information from Python script
get_project_list() {
    python3 "$(dirname "${BASH_SOURCE[0]}")/fusesoc_build.py" --list-projects 2>/dev/null || {
        echo "Available projects:"
        echo "  pin-tester          - Hardware verification tool for testing all FPGA pins"
        echo "  sharp-organizer-card - Interface for Sharp electronic organizers"
    }
}

# Print usage information with project list
print_usage() {
    local script_name="$1"
    echo "Usage: $script_name <project_name> [options]"
    echo ""
    get_project_list
    echo ""
    echo "Options:"
    echo "  LOG_LEVEL=DEBUG     - Enable debug logging"
    echo ""
    echo "Examples:"
    echo "  $script_name pin-tester"
    echo "  LOG_LEVEL=DEBUG $script_name sharp-organizer-card"
}

# Validate project name using Python script
validate_project() {
    local project_name="$1"
    python3 "$(dirname "${BASH_SOURCE[0]}")/fusesoc_build.py" --validate-project "$project_name" 2>/dev/null
}

# Print error message and usage, then exit
usage_error() {
    local message="$1"
    local script_name="$2"
    echo "Error: $message"
    echo ""
    print_usage "$script_name"
    exit 1
}