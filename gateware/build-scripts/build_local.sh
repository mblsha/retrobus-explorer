#!/bin/bash
# Local build wrapper that runs the build on Windows and copies results back

set -e

# Source common functions
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

# Check if project name was provided
if [ $# -eq 0 ]; then
    usage_error "No project name provided" "$0"
fi

PROJECT_NAME=$1
shift

# Validate project name
if ! validate_project "$PROJECT_NAME"; then
    usage_error "Unknown project '$PROJECT_NAME'" "$0"
fi

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR/../.."

# Check for .env file
if [ ! -f ".env" ]; then
    echo "Error: .env file not found"
    echo "Please create .env with your SSH/SCP settings"
    exit 1
fi

# Load environment variables
source .env

# Check required variables
if [ -z "$SSH_USER" ] || [ -z "$SSH_HOST" ] || [ -z "$SSH_PORT" ]; then
    echo "Error: SSH settings not found in .env"
    exit 1
fi

if [ -z "$SCP_USER" ] || [ -z "$SCP_HOST" ] || [ -z "$SCP_PORT" ]; then
    echo "Error: SCP settings not found in .env"
    exit 1
fi

if [ -z "$WINDOWS_PROJECT_PATH" ]; then
    echo "Error: WINDOWS_PROJECT_PATH not found in .env"
    echo "Please add: WINDOWS_PROJECT_PATH=/mnt/c/Users/your_username/src/retrobus-explorer"
    exit 1
fi

echo "=== RetroBus Explorer Local Build ==="
echo "Project: $PROJECT_NAME"
echo ""
echo "Running build on Windows WSL..."

# Run the build on Windows
ssh -p $SSH_PORT ${SSH_USER}@${SSH_HOST} "cd $WINDOWS_PROJECT_PATH && ./gateware/build-scripts/build_fusesoc.sh $PROJECT_NAME $*"

# Check if build succeeded
if [ $? -eq 0 ]; then
    echo ""
    echo "Build completed on Windows. Copying bitstream to local machine..."
    
    # Create local bitstreams directory
    mkdir -p bitstreams
    
    # Convert project name to safe filename
    SAFE_NAME=$(echo $PROJECT_NAME | tr '-' '_')
    
    # Copy the bitstream
    scp -P $SCP_PORT ${SCP_USER}@${SCP_HOST}:${WINDOWS_PROJECT_PATH}/bitstreams/${SAFE_NAME}_latest.bit bitstreams/
    
    if [ $? -eq 0 ]; then
        echo ""
        echo "Build completed successfully!"
        echo "Bitstream available locally at: bitstreams/${SAFE_NAME}_latest.bit"
        ls -la bitstreams/${SAFE_NAME}_latest.bit
        
        # Also copy the timestamped version if it exists
        LATEST_TIMESTAMPED=$(ssh -p $SSH_PORT ${SSH_USER}@${SSH_HOST} "cd ${WINDOWS_PROJECT_PATH}/bitstreams && ls -t ${SAFE_NAME}_2*.bit 2>/dev/null | head -1")
        if [ -n "$LATEST_TIMESTAMPED" ]; then
            scp -P $SCP_PORT ${SCP_USER}@${SCP_HOST}:${WINDOWS_PROJECT_PATH}/bitstreams/$LATEST_TIMESTAMPED bitstreams/
            echo "Also copied: bitstreams/$LATEST_TIMESTAMPED"
        fi
    else
        echo "Error: Failed to copy bitstream from Windows"
        exit 1
    fi
else
    echo ""
    echo "Build failed on Windows. Check remote logs for details."
    exit 1
fi