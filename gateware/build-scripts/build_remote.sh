#!/bin/bash
# Remote build wrapper that copies gateware to Windows and runs the build
# No need for a full repository checkout on the Windows side

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

# Get script directory and navigate to repository root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$( cd "$SCRIPT_DIR/../.." && pwd )"
cd "$REPO_ROOT"

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
    echo "Please set SSH_USER, SSH_HOST, and SSH_PORT in .env"
    exit 1
fi

if [ -z "$SCP_USER" ] || [ -z "$SCP_HOST" ] || [ -z "$SCP_PORT" ]; then
    echo "Error: SCP settings not found in .env"
    echo "Please set SCP_USER, SCP_HOST, and SCP_PORT in .env"
    exit 1
fi

# Use a simple remote working directory instead of requiring full checkout
REMOTE_WORK_DIR="${REMOTE_WORK_DIR:-/tmp/retrobus-build-$$}"

echo "=== RetroBus Explorer Remote Build ==="
echo "Project: $PROJECT_NAME"
echo "Remote work directory: $REMOTE_WORK_DIR"
echo ""

# Create unique timestamp for this build
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BUILD_ID="${PROJECT_NAME}_${TIMESTAMP}"

echo "Step 1/5: Preparing remote work directory..."
ssh -p $SSH_PORT ${SSH_USER}@${SSH_HOST} "mkdir -p $REMOTE_WORK_DIR"

echo "Step 2/5: Packaging and copying gateware to Windows..."
echo "  Creating compressed archive..."

# Create a temporary archive with gateware and .env (exclude macOS metadata)
TEMP_ARCHIVE="retrobus-build-${BUILD_ID}.tar.gz"
tar -czf "$TEMP_ARCHIVE" --exclude='._*' --exclude='.DS_Store' --no-xattrs gateware/ .env

echo "  Copying: ${TEMP_ARCHIVE} -> ${SSH_HOST}:${REMOTE_WORK_DIR}/"
scp -P $SCP_PORT "$TEMP_ARCHIVE" ${SCP_USER}@${SCP_HOST}:${REMOTE_WORK_DIR}/

# Clean up local archive
rm "$TEMP_ARCHIVE"

echo "  Extracting archive on remote..."
ssh -p $SSH_PORT ${SSH_USER}@${SSH_HOST} "cd ${REMOTE_WORK_DIR} && tar -xzf ${TEMP_ARCHIVE} && rm ${TEMP_ARCHIVE}"

echo "Step 3/5: Setting up build environment on Windows..."
# Create a simple build wrapper script on the remote side
ssh -p $SSH_PORT ${SSH_USER}@${SSH_HOST} "cat > ${REMOTE_WORK_DIR}/remote_build.sh << 'EOF'
#!/bin/bash
set -e

cd \"$REMOTE_WORK_DIR\"

# Source environment
source .env

# Check for required tools
echo \"Checking build prerequisites...\"

if ! command -v python3 &> /dev/null; then
    echo \"Error: Python 3 not found\"
    exit 1
fi

if ! command -v sbt &> /dev/null; then
    echo \"Error: SBT not found. Please install it first:\"
    echo \"  # Add SBT repository\"
    echo '  echo \"deb https://repo.scala-sbt.org/scalasbt/debian all main\" | sudo tee /etc/apt/sources.list.d/sbt.list'
    echo '  echo \"deb https://repo.scala-sbt.org/scalasbt/debian /\" | sudo tee /etc/apt/sources.list.d/sbt_old.list'
    echo '  curl -sL \"https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x2EE0EA64E40A89B84B2DF73499E82A75642AC823\" | sudo apt-key add'
    echo \"  sudo apt-get update && sudo apt-get install sbt\"
    exit 1
fi

# Set up Python environment
if [ -n \"\$FUSESOC_PYENV\" ]; then
    echo \"Setting up pyenv environment: \$FUSESOC_PYENV\"
    export PYENV_VERSION=\$FUSESOC_PYENV
    export PATH=\"\$HOME/.pyenv/versions/\$FUSESOC_PYENV/bin:\$PATH\"
else
    # Ensure local pip packages are in PATH
    export PATH=\"\$HOME/.local/bin:\$PATH\"
fi

if ! python3 -c \"import fusesoc\" &> /dev/null; then
    echo \"FuseSoC not found. Installing...\"
    python3 -m pip install fusesoc
fi

# Make sure fusesoc is available in PATH or use python module
if ! command -v fusesoc &> /dev/null; then
    echo \"Setting up FuseSoC alias...\"
    alias fusesoc=\"python3 -m fusesoc\"
fi

echo \"Prerequisites check completed.\"
echo \"\"

# Run the build
echo \"Starting build for project: $PROJECT_NAME\"
cd gateware

# Make sure we have the build scripts executable
chmod +x build-scripts/*.sh build-scripts/*.py

# Create a corrected fusesoc config for the gateware directory
echo \"Creating FuseSoC configuration for gateware directory...\"
cat > fusesoc_gateware.conf << 'FUSESOC_EOF'
[main]
build_root = build_fusesoc
cache_root = .fusesoc_cache
library_root = libraries

[library.retrobus]
location = chisel/cores
sync-uri = chisel/cores
sync-type = local
auto-sync = true

[tool.vivado]
path = ../vivado_wsl_wrapper.py
jobs = 8
FUSESOC_EOF

export FUSESOC_CONFIG=\"fusesoc_gateware.conf\"
echo \"Using FuseSoC config: \$FUSESOC_CONFIG\"

./build-scripts/build_local.sh $PROJECT_NAME $* 2>&1 | tee /tmp/retrobus_build_output_$$.log
BUILD_EXIT=\${PIPESTATUS[0]}

# Save information about where logs might be
echo "Build exit code: \$BUILD_EXIT" > /tmp/retrobus_build_info_$$.txt
echo "Working directory: \$(pwd)" >> /tmp/retrobus_build_info_$$.txt
echo "Build output saved to: /tmp/retrobus_build_output_$$.log" >> /tmp/retrobus_build_info_$$.txt

# Try to find vivado_calls.log and other important logs
find . -name "vivado_calls.log" -o -name "*.rpt" -o -name "vivado.log" 2>/dev/null | head -20 >> /tmp/retrobus_build_info_$$.txt

exit \$BUILD_EXIT
EOF

chmod +x \"$REMOTE_WORK_DIR/remote_build.sh\""

echo "Step 4/5: Running build on Windows WSL..."
ssh -p $SSH_PORT ${SSH_USER}@${SSH_HOST} "$REMOTE_WORK_DIR/remote_build.sh"

# Check if build succeeded
if [ $? -eq 0 ]; then
    echo ""
    echo "Step 5/5: Copying results back to local machine..."
    
    # Create local directories
    mkdir -p bitstreams logs
    
    # Convert project name to safe filename (matching Python script convention)
    SAFE_NAME=$(echo $PROJECT_NAME | tr '-' '_')
    
    echo "  Copying bitstreams..."
    # Copy the latest bitstream from gateware/bitstreams directory
    scp -P $SCP_PORT ${SCP_USER}@${SCP_HOST}:${REMOTE_WORK_DIR}/gateware/bitstreams/${SAFE_NAME}_latest.bit bitstreams/ 2>/dev/null || {
        echo "  Warning: Latest bitstream not found, looking for timestamped versions..."
        # Try to copy any timestamped bitstream
        LATEST_TIMESTAMPED=$(ssh -p $SSH_PORT ${SSH_USER}@${SSH_HOST} "ls -t ${REMOTE_WORK_DIR}/gateware/bitstreams/${SAFE_NAME}_*.bit 2>/dev/null | head -1" || echo "")
        if [ -n "$LATEST_TIMESTAMPED" ]; then
            BASENAME=$(basename "$LATEST_TIMESTAMPED")
            scp -P $SCP_PORT ${SCP_USER}@${SCP_HOST}:"$LATEST_TIMESTAMPED" bitstreams/
            # Also create a "latest" symlink
            ln -sf "$BASENAME" "bitstreams/${SAFE_NAME}_latest.bit"
            echo "  Copied: bitstreams/$BASENAME"
        else
            echo "  Error: No bitstream found!"
            exit 1
        fi
    }
    
    # Copy build logs
    echo "  Copying build logs..."
    scp -P $SCP_PORT ${SCP_USER}@${SCP_HOST}:${REMOTE_WORK_DIR}/gateware/logs/fusesoc_${PROJECT_NAME}_*.log logs/ 2>/dev/null || {
        echo "  Warning: Build logs not found"
    }
    
    # Copy any timestamped bitstreams that exist
    TIMESTAMPED_BITS=$(ssh -p $SSH_PORT ${SSH_USER}@${SSH_HOST} "ls ${REMOTE_WORK_DIR}/gateware/bitstreams/${SAFE_NAME}_2*.bit 2>/dev/null" || echo "")
    if [ -n "$TIMESTAMPED_BITS" ]; then
        echo "  Copying timestamped bitstreams..."
        scp -P $SCP_PORT ${SCP_USER}@${SCP_HOST}:${REMOTE_WORK_DIR}/gateware/bitstreams/${SAFE_NAME}_2*.bit bitstreams/ 2>/dev/null || true
    fi
    
    echo ""
    echo "Build completed successfully!"
    echo "Bitstream available locally at: bitstreams/${SAFE_NAME}_latest.bit"
    
    if [ -f "bitstreams/${SAFE_NAME}_latest.bit" ]; then
        ls -la bitstreams/${SAFE_NAME}_latest.bit
    fi
    
    # Show available bitstreams
    echo ""
    echo "Available bitstreams:"
    ls -la bitstreams/${SAFE_NAME}*.bit 2>/dev/null || echo "  No bitstreams found"
    
    # Cleanup remote directory
    echo ""
    echo "Cleaning up remote work directory..."
    ssh -p $SSH_PORT ${SSH_USER}@${SSH_HOST} "rm -rf $REMOTE_WORK_DIR" || {
        echo "Warning: Failed to cleanup remote directory $REMOTE_WORK_DIR"
    }
    
else
    echo ""
    echo "Build failed on Windows. Collecting diagnostic information..."
    
    # Create local directories for logs
    mkdir -p logs
    mkdir -p logs/vivado_logs
    
    # Try to copy all relevant logs even if build failed
    echo "  Copying FuseSoC logs..."
    scp -P $SCP_PORT ${SCP_USER}@${SCP_HOST}:${REMOTE_WORK_DIR}/gateware/logs/fusesoc_${PROJECT_NAME}_*.log logs/ 2>/dev/null || {
        echo "  No FuseSoC logs found"
    }
    
    # Copy Vivado logs if they exist
    echo "  Copying Vivado logs..."
    scp -P $SCP_PORT ${SCP_USER}@${SCP_HOST}:${REMOTE_WORK_DIR}/gateware/vivado_calls.log logs/ 2>/dev/null || {
        echo "  No vivado_calls.log found in gateware directory"
    }
    
    # Copy the build output and info files
    echo "  Copying build output log..."
    scp -P $SCP_PORT ${SCP_USER}@${SCP_HOST}:/tmp/retrobus_build_output_$$.log logs/ 2>/dev/null || {
        echo "  No build output log found"
    }
    scp -P $SCP_PORT ${SCP_USER}@${SCP_HOST}:/tmp/retrobus_build_info_$$.txt logs/ 2>/dev/null || {
        echo "  No build info file found"
    }
    
    # Copy build directories that might contain useful logs
    echo "  Copying build artifacts..."
    BUILD_DIR="${REMOTE_WORK_DIR}/gateware/build_fusesoc"
    
    # Find the specific build directory for this core
    CORE_NAME=$(echo $PROJECT_NAME | tr '-' ':')
    FUSESOC_CORE="retrobus:projects:${CORE_NAME}"
    
    # Try to copy the entire build directory for analysis
    ssh -p $SSH_PORT ${SSH_USER}@${SSH_HOST} "cd ${BUILD_DIR} && find . -name '*.log' -o -name '*.rpt' -o -name 'Makefile' | head -50" 2>/dev/null | while read -r logfile; do
        if [ -n "$logfile" ]; then
            echo "    Found: $logfile"
            # Create directory structure locally
            LOCAL_DIR="logs/build_artifacts/$(dirname "$logfile")"
            mkdir -p "$LOCAL_DIR"
            scp -P $SCP_PORT ${SCP_USER}@${SCP_HOST}:"${BUILD_DIR}/${logfile}" "$LOCAL_DIR/" 2>/dev/null || true
        fi
    done
    
    # Try to get the vivado project directory logs
    echo "  Looking for Vivado project logs..."
    ssh -p $SSH_PORT ${SSH_USER}@${SSH_HOST} "find ${BUILD_DIR} -name 'vivado.log' -o -name 'runme.log' -o -name 'vivado_calls.log' 2>/dev/null | head -20" 2>/dev/null | while read -r viv_log; do
        if [ -n "$viv_log" ]; then
            echo "    Found Vivado log: $viv_log"
            LOG_NAME=$(basename "$viv_log")
            # For vivado_calls.log, preserve the path structure in the filename
            if [ "$LOG_NAME" = "vivado_calls.log" ]; then
                LOG_NAME="vivado_calls_$(echo "$viv_log" | sed 's|/|_|g' | sed 's|.*build_fusesoc_||').log"
            fi
            scp -P $SCP_PORT ${SCP_USER}@${SCP_HOST}:"$viv_log" "logs/vivado_logs/$LOG_NAME" 2>/dev/null || true
        fi
    done
    
    # Get directory listing for debugging
    echo "  Getting remote directory structure..."
    ssh -p $SSH_PORT ${SSH_USER}@${SSH_HOST} "ls -la ${REMOTE_WORK_DIR}/gateware/" > logs/remote_gateware_listing.txt 2>/dev/null || true
    ssh -p $SSH_PORT ${SSH_USER}@${SSH_HOST} "find ${BUILD_DIR} -type f -name '*.log' -o -name '*.rpt' -o -name 'Makefile' | sort" > logs/remote_build_files.txt 2>/dev/null || true
    
    # Get the actual error from the build
    echo ""
    echo "Attempting to get specific error information..."
    ssh -p $SSH_PORT ${SSH_USER}@${SSH_HOST} "cd ${BUILD_DIR} && find . -name 'Makefile' -exec grep -l 'retrobus' {} \; | head -1" 2>/dev/null | read -r MAKEFILE_PATH
    if [ -n "$MAKEFILE_PATH" ]; then
        echo "  Found Makefile at: $MAKEFILE_PATH"
        ssh -p $SSH_PORT ${SSH_USER}@${SSH_HOST} "cd ${BUILD_DIR}/$(dirname $MAKEFILE_PATH) && make -n" > logs/make_dry_run.txt 2>&1 || true
    fi
    
    # Cleanup remote directory even on failure
    echo ""
    echo "Cleaning up remote work directory..."
    ssh -p $SSH_PORT ${SSH_USER}@${SSH_HOST} "rm -rf $REMOTE_WORK_DIR" || true
    
    echo ""
    echo "Build failed. Diagnostic information collected in logs/ directory:"
    echo "  - FuseSoC logs: logs/fusesoc_*.log"
    echo "  - Build output: logs/retrobus_build_output_*.log"
    echo "  - Build info: logs/retrobus_build_info_*.txt"
    echo "  - Vivado logs: logs/vivado_logs/"
    echo "  - Build artifacts: logs/build_artifacts/"
    echo "  - Directory listings: logs/remote_*.txt"
    echo ""
    echo "To find specific Vivado logs, check:"
    echo "  - logs/vivado_logs/vivado_calls_*.log"
    echo "  - logs/build_artifacts/**/vivado_calls.log"
    exit 1
fi