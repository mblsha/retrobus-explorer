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
pwd >> /tmp/retrobus_build_info_$$.txt
echo "Build output saved to: /tmp/retrobus_build_output_$$.log" >> /tmp/retrobus_build_info_$$.txt

# Try to find vivado_calls.log and other important logs
find . -name "vivado_calls.log" -o -name "*.rpt" -o -name "vivado.log" 2>/dev/null | head -20 >> /tmp/retrobus_build_info_$$.txt

exit \$BUILD_EXIT
EOF

chmod +x \"$REMOTE_WORK_DIR/remote_build.sh\""

collect_diagnostic_logs() {
    local step_desc="$1"
    echo "  $step_desc: Collecting diagnostic logs..."
    
    # Create timestamp for this build session
    local TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    local ARCHIVE_NAME="build_diagnostics_${PROJECT_NAME}_${TIMESTAMP}"
    local LOCAL_EXTRACT_DIR="logs/${PROJECT_NAME}_${TIMESTAMP}"
    
    echo "    Creating comprehensive diagnostic archive on remote..."
    
    # Create archive on remote side with all diagnostic information
    ssh -p $SSH_PORT ${SSH_USER}@${SSH_HOST} "
        cd '${REMOTE_WORK_DIR}'
        
        # Create archive directory structure
        mkdir -p '/tmp/${ARCHIVE_NAME}/{fusesoc_logs,vivado_logs,build_artifacts,metadata}'
        
        # Copy FuseSoC logs
        cp gateware/logs/fusesoc_${PROJECT_NAME}_*.log '/tmp/${ARCHIVE_NAME}/fusesoc_logs/' 2>/dev/null || echo 'No FuseSoC logs found'
        
        # Copy build output and info files
        cp '/tmp/retrobus_build_output_\$\$.log' '/tmp/${ARCHIVE_NAME}/build_output.log' 2>/dev/null || echo 'No build output'
        cp '/tmp/retrobus_build_info_\$\$.txt' '/tmp/${ARCHIVE_NAME}/build_info.txt' 2>/dev/null || echo 'No build info'
        
        # Copy main Vivado log if it exists
        cp gateware/vivado_calls.log '/tmp/${ARCHIVE_NAME}/vivado_logs/' 2>/dev/null || echo 'No main vivado_calls.log'
        
        # Copy entire build directory structure preserving paths
        if [ -d gateware/build_fusesoc ]; then
            cp -r gateware/build_fusesoc '/tmp/${ARCHIVE_NAME}/build_artifacts/' 2>/dev/null || echo 'No build artifacts'
        fi
        
        # Generate metadata
        echo 'Build session: ${PROJECT_NAME}' > '/tmp/${ARCHIVE_NAME}/metadata/session_info.txt'
        echo 'Timestamp: ${TIMESTAMP}' >> '/tmp/${ARCHIVE_NAME}/metadata/session_info.txt'
        echo 'Remote work dir: ${REMOTE_WORK_DIR}' >> '/tmp/${ARCHIVE_NAME}/metadata/session_info.txt'
        echo \"Build host: \\\$(hostname)\" >> '/tmp/${ARCHIVE_NAME}/metadata/session_info.txt'
        echo '' >> '/tmp/${ARCHIVE_NAME}/metadata/session_info.txt'
        
        # Directory listings
        echo '=== Gateware Directory ===' > '/tmp/${ARCHIVE_NAME}/metadata/directory_listings.txt'
        ls -la gateware/ >> '/tmp/${ARCHIVE_NAME}/metadata/directory_listings.txt' 2>/dev/null
        echo '' >> '/tmp/${ARCHIVE_NAME}/metadata/directory_listings.txt'
        echo '=== Build Directory Structure ===' >> '/tmp/${ARCHIVE_NAME}/metadata/directory_listings.txt'
        find gateware/build_fusesoc -type f -name '*.log' -o -name '*.rpt' -o -name 'Makefile' 2>/dev/null | sort >> '/tmp/${ARCHIVE_NAME}/metadata/directory_listings.txt'
        
        # Create compressed archive
        cd /tmp
        tar -czf '${ARCHIVE_NAME}.tar.gz' '${ARCHIVE_NAME}/'
        rm -rf '${ARCHIVE_NAME}/'
        
        echo 'Archive created: /tmp/${ARCHIVE_NAME}.tar.gz'
        ls -lh '/tmp/${ARCHIVE_NAME}.tar.gz'
    "
    
    echo "    Copying archive to local machine..."
    mkdir -p logs
    scp -P $SCP_PORT ${SCP_USER}@${SCP_HOST}:/tmp/${ARCHIVE_NAME}.tar.gz logs/ || {
        echo "    ERROR: Failed to copy diagnostic archive"
        return 1
    }
    
    echo "    Extracting archive to ${LOCAL_EXTRACT_DIR}..."
    cd logs
    tar -xzf ${ARCHIVE_NAME}.tar.gz
    mv ${ARCHIVE_NAME} $(basename ${LOCAL_EXTRACT_DIR})
    rm ${ARCHIVE_NAME}.tar.gz
    cd ..
    
    echo "    Cleaning up remote archive..."
    ssh -p $SSH_PORT ${SSH_USER}@${SSH_HOST} "rm -f /tmp/${ARCHIVE_NAME}.tar.gz" 2>/dev/null || true
    
    echo "    ✅ Diagnostic logs extracted to: ${LOCAL_EXTRACT_DIR}"
    echo "       Key files:"
    echo "         - ${LOCAL_EXTRACT_DIR}/build_output.log (complete build output)"
    echo "         - ${LOCAL_EXTRACT_DIR}/vivado_logs/ (Vivado execution logs)"
    echo "         - ${LOCAL_EXTRACT_DIR}/build_artifacts/ (complete build tree)"
    echo "         - ${LOCAL_EXTRACT_DIR}/metadata/ (build session info)"
}

echo "Step 4/5: Running build on Windows WSL..."
ssh -p $SSH_PORT ${SSH_USER}@${SSH_HOST} "$REMOTE_WORK_DIR/remote_build.sh"
BUILD_RESULT=$?

echo ""
echo "Step 5/5: Collecting results and diagnostic information..."

# Always collect logs regardless of build outcome
collect_diagnostic_logs "Always"

# Check if build succeeded and copy artifacts
if [ $BUILD_RESULT -eq 0 ]; then
    echo "  BUILD SUCCESSFUL: Copying bitstreams..."
    
    # Create bitstreams directory
    mkdir -p bitstreams
    
    # Convert project name to safe filename (matching Python script convention)
    SAFE_NAME=$(echo $PROJECT_NAME | tr '-' '_')
    
    # Copy the latest bitstream from gateware/bitstreams directory
    scp -P $SCP_PORT ${SCP_USER}@${SCP_HOST}:${REMOTE_WORK_DIR}/gateware/bitstreams/${SAFE_NAME}_latest.bit bitstreams/ 2>/dev/null || {
        echo "    Warning: Latest bitstream not found, looking for timestamped versions..."
        # Try to copy any timestamped bitstream
        LATEST_TIMESTAMPED=$(ssh -p $SSH_PORT ${SSH_USER}@${SSH_HOST} "ls -t ${REMOTE_WORK_DIR}/gateware/bitstreams/${SAFE_NAME}_*.bit 2>/dev/null | head -1" || echo "")
        if [ -n "$LATEST_TIMESTAMPED" ]; then
            BASENAME=$(basename "$LATEST_TIMESTAMPED")
            scp -P $SCP_PORT ${SCP_USER}@${SCP_HOST}:"$LATEST_TIMESTAMPED" bitstreams/
            # Also create a "latest" symlink
            ln -sf "$BASENAME" "bitstreams/${SAFE_NAME}_latest.bit"
            echo "    Copied: bitstreams/$BASENAME"
        else
            echo "    Warning: No bitstream found! Check logs for synthesis/implementation errors."
        fi
    }
    
    # Copy any timestamped bitstreams that exist
    TIMESTAMPED_BITS=$(ssh -p $SSH_PORT ${SSH_USER}@${SSH_HOST} "ls ${REMOTE_WORK_DIR}/gateware/bitstreams/${SAFE_NAME}_2*.bit 2>/dev/null" || echo "")
    if [ -n "$TIMESTAMPED_BITS" ]; then
        echo "    Copying additional timestamped bitstreams..."
        scp -P $SCP_PORT ${SCP_USER}@${SCP_HOST}:${REMOTE_WORK_DIR}/gateware/bitstreams/${SAFE_NAME}_2*.bit bitstreams/ 2>/dev/null || true
    fi
    
    echo ""
    echo "✅ Build completed successfully!"
    echo ""
    echo "🎯 Bitstream: bitstreams/${SAFE_NAME}_latest.bit"
    
    if [ -f "bitstreams/${SAFE_NAME}_latest.bit" ]; then
        ls -la bitstreams/${SAFE_NAME}_latest.bit
    fi
    
    # Show available bitstreams
    echo ""
    echo "📦 Available bitstreams:"
    ls -la bitstreams/${SAFE_NAME}*.bit 2>/dev/null || echo "  No bitstreams found"
    
    echo ""
    echo "📋 Build logs and diagnostics also collected in: logs/${PROJECT_NAME}_$(date +%Y%m%d_%H%M%S)*"
    echo "   (useful for timing analysis, resource utilization, etc.)"
    
    # Cleanup remote directory
    echo ""
    echo "Cleaning up remote work directory..."
    ssh -p $SSH_PORT ${SSH_USER}@${SSH_HOST} "rm -rf $REMOTE_WORK_DIR" || {
        echo "Warning: Failed to cleanup remote directory $REMOTE_WORK_DIR"
    }
    
else
    echo "  BUILD FAILED: Error code $BUILD_RESULT"
    echo ""
    echo "❌ Build failed. All diagnostic information has been collected in a timestamped directory."
    echo ""
    echo "📁 Check the logs/${PROJECT_NAME}_$(date +%Y%m%d_%H%M%S)* directory for:"
    echo "   • build_output.log - Complete build output with real-time Vivado logs"
    echo "   • build_artifacts/ - Full FuseSoC build tree with all reports"
    echo "   • vivado_logs/ - Vivado execution logs"
    echo "   • fusesoc_logs/ - FuseSoC build logs"
    echo "   • metadata/ - Build session information"
    echo ""
    echo "🔍 Most likely places to find the error:"
    echo "   • build_output.log (search for 'ERROR:' or 'CRITICAL WARNING:')"
    echo "   • build_artifacts/build_fusesoc/*/default/logs/vivado_calls.log"
fi

# Cleanup remote directory 
echo ""
echo "Cleaning up remote work directory..."
ssh -p $SSH_PORT ${SSH_USER}@${SSH_HOST} "rm -rf $REMOTE_WORK_DIR" || {
    echo "Warning: Failed to cleanup remote directory $REMOTE_WORK_DIR"
}

# Exit with the build result
if [ $BUILD_RESULT -ne 0 ]; then
    echo ""
    echo "Build process failed. Check the logs above for detailed error information."
    exit $BUILD_RESULT
fi