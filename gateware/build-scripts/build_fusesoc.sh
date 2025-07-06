#!/bin/bash
# Generic FuseSoC build wrapper for WSL environment

set -e

# Source common functions
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

# Check if project name was provided
if [ $# -eq 0 ]; then
    usage_error "No project name provided" "$0"
fi

PROJECT_NAME=$1
shift  # Remove project name from arguments

# Validate project name
if ! validate_project "$PROJECT_NAME"; then
    usage_error "Unknown project '$PROJECT_NAME'" "$0"
fi

echo "=== RetroBus Explorer FuseSoC Build ==="
echo "Project: $PROJECT_NAME"

# Check if we're in WSL
if [ ! -d "/mnt/c" ]; then
    echo "Error: This script must be run from WSL"
    exit 1
fi

# Get to repository root (two levels up from build-scripts)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$( cd "$SCRIPT_DIR/../.." && pwd )"
cd "$REPO_ROOT"

# Check for .env file
if [ ! -f ".env" ]; then
    echo "Error: .env file not found in repository root"
    echo "Please copy .env.example to .env and configure it:"
    echo "  cp .env.example .env"
    echo "  nano .env"
    exit 1
fi

# Source the .env file to set up pyenv
source .env

# Check if running in fish shell
if [ -n "$FISH_VERSION" ]; then
    echo "Detected fish shell"
    # Set up pyenv for fish
    pyenv local $FUSESOC_PYENV
    set -x PATH $HOME/.pyenv/versions/$FUSESOC_PYENV/bin $PATH
else
    # Bash/sh setup
    export PYENV_VERSION=$FUSESOC_PYENV
    export PATH="$HOME/.pyenv/versions/$FUSESOC_PYENV/bin:$PATH"
fi

# Check for required tools
echo "Checking prerequisites..."

if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 not found in pyenv environment"
    exit 1
fi

if ! command -v fusesoc &> /dev/null; then
    echo "FuseSoC not found. Installing..."
    python3 -m pip install fusesoc
fi

if ! command -v sbt &> /dev/null; then
    echo "Error: SBT not found. Please install it first:"
    echo "  # Add SBT repository"
    echo '  echo "deb https://repo.scala-sbt.org/scalasbt/debian all main" | sudo tee /etc/apt/sources.list.d/sbt.list'
    echo '  echo "deb https://repo.scala-sbt.org/scalasbt/debian /" | sudo tee /etc/apt/sources.list.d/sbt_old.list'
    echo '  curl -sL "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x2EE0EA64E40A89B84B2DF73499E82A75642AC823" | sudo apt-key add'
    echo "  sudo apt-get update && sudo apt-get install sbt"
    exit 1
fi

# Run the Python build script with the project name
echo "Starting build process for $PROJECT_NAME..."
python3 "$SCRIPT_DIR/fusesoc_build.py" "$PROJECT_NAME" "$@"

# Check exit status
if [ $? -eq 0 ]; then
    echo ""
    echo "Build completed successfully!"
    echo "Check logs/ directory for detailed build logs"
    echo "Bitstream available at: bitstreams/${PROJECT_NAME}_latest.bit"
    
else
    echo ""
    echo "Build failed! Check logs for details"
    exit 1
fi