#!/bin/bash
set -e

# Test script for Alchitry CI container
# This script runs the same checks as GitHub Actions but locally

echo "🧪 Testing Alchitry CI container locally..."

# Get the project root (two levels up from this script)
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

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

# Function to run checks for a single project
check_project() {
    local project=$1
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🔍 Checking project: $project"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # Detect container runtime (Docker or Apple container)
    if command -v docker &> /dev/null; then
        CONTAINER_CMD="docker"
    elif command -v container &> /dev/null; then
        CONTAINER_CMD="container"
    else
        echo "❌ No container runtime found (docker or container)"
        exit 1
    fi
    
    $CONTAINER_CMD run --rm \
        --volume "$PROJECT_ROOT:/workspace" \
        retrobus-alchitry-ci \
        bash -c "
            cd /workspace/gateware/$project
            echo 'Checking project: $project'
            
            # Check if project file exists
            PROJECT_FILE='$project.alp'
            if [ ! -f \"\$PROJECT_FILE\" ]; then
                echo '❌ Error: Project file \$PROJECT_FILE not found'
                exit 1
            fi
            
            echo '✅ Found project file: '\$PROJECT_FILE
            
            # Run syntax check
            echo '🔧 Running syntax check...'
            PROJECT_ABS_PATH=\"\$(pwd)/\$PROJECT_FILE\"
            
            if \"\$ALCHITRY_BIN\" check \"\$PROJECT_ABS_PATH\" 2>&1 | tee check_output.log; then
                if grep -q 'Failed to open project' check_output.log; then
                    echo '❌ Project check failed - could not open project file'
                    cat check_output.log
                    exit 1
                elif grep -q 'error\|Error\|ERROR' check_output.log; then
                    echo '❌ Project check failed - errors found'
                    cat check_output.log
                    exit 1
                else
                    echo '✅ Project syntax check completed successfully'
                fi
            else
                echo '❌ alchitry command failed with exit code \$?'
                exit 1
            fi
            
            # Run test benches if available
            echo ''
            echo '🧪 Checking for test benches...'
            if \"\$ALCHITRY_BIN\" sim \"\$PROJECT_ABS_PATH\" --list 2>&1 | grep -q 'Tests:'; then
                echo '📋 Test benches found, running simulation tests...'
                
                if \"\$ALCHITRY_BIN\" sim \"\$PROJECT_ABS_PATH\" 2>&1 | tee sim_output.log; then
                    if grep -q 'failed\|Failed\|FAILED\|Error\|ERROR' sim_output.log; then
                        echo '❌ Test bench execution failed'
                        cat sim_output.log
                        exit 1
                    elif grep -q 'passed!' sim_output.log; then
                        echo '✅ All test benches passed successfully'
                        grep 'passed!' sim_output.log
                    else
                        echo '⚠️ Test benches ran but no clear pass/fail indication found'
                        cat sim_output.log
                    fi
                else
                    echo '❌ Test bench execution failed with exit code \$?'
                    exit 1
                fi
            else
                echo 'ℹ️ No test benches found for project $project'
            fi
            
            echo '✅ Project $project passed all checks!'
        "
    
    return $?
}

# Track results
FAILED_PROJECTS=()
PASSED_PROJECTS=()

# Run checks for each project
for project in "${PROJECTS[@]}"; do
    if check_project "$project"; then
        PASSED_PROJECTS+=("$project")
    else
        FAILED_PROJECTS+=("$project")
    fi
done

# Summary
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 Test Summary"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ ${#PASSED_PROJECTS[@]} -gt 0 ]; then
    echo "✅ Passed (${#PASSED_PROJECTS[@]}): ${PASSED_PROJECTS[*]}"
fi

if [ ${#FAILED_PROJECTS[@]} -gt 0 ]; then
    echo "❌ Failed (${#FAILED_PROJECTS[@]}): ${FAILED_PROJECTS[*]}"
    exit 1
else
    echo "🎉 All projects passed!"
fi