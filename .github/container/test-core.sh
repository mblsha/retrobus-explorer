#!/bin/bash
# Core testing logic for Alchitry projects
# This script contains the shared testing functions used by both
# local container testing and GitHub Actions CI

# Function to check a single project
# Arguments:
#   $1 - project name
#   $2 - project directory path
#   $3 - alchitry binary path
# Returns:
#   0 on success, 1 on failure
check_project() {
    local project=$1
    local project_dir=$2
    local alchitry_bin=$3
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🔍 Checking project: $project"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    cd "$project_dir" || return 1
    echo "Checking project: $project"
    
    # Check if project file exists
    PROJECT_FILE="$project.alp"
    if [ ! -f "$PROJECT_FILE" ]; then
        echo "❌ Error: Project file $PROJECT_FILE not found"
        return 1
    fi
    
    echo "✅ Found project file: $PROJECT_FILE"
    
    # Run syntax check
    echo "🔧 Running syntax check..."
    PROJECT_ABS_PATH="$(pwd)/$PROJECT_FILE"
    
    if "$alchitry_bin" check "$PROJECT_ABS_PATH" 2>&1 | tee check_output.log; then
        # Check if the output contains failure messages
        if grep -q "Failed to open project" check_output.log; then
            echo "❌ Project check failed - could not open project file"
            cat check_output.log
            return 1
        elif grep -q "error\|Error\|ERROR" check_output.log; then
            echo "❌ Project check failed - errors found"
            cat check_output.log
            return 1
        else
            echo "✅ Project syntax check completed successfully"
        fi
    else
        echo "❌ alchitry command failed with exit code $?"
        return 1
    fi
    
    # Run test benches if available
    echo ""
    echo "🧪 Checking for test benches..."
    if "$alchitry_bin" sim "$PROJECT_ABS_PATH" --list 2>&1 | grep -q "Tests:"; then
        echo "📋 Test benches found, running simulation tests..."
        
        if "$alchitry_bin" sim "$PROJECT_ABS_PATH" 2>&1 | tee sim_output.log; then
            # Check if any tests failed
            if grep -q "failed\|Failed\|FAILED\|Error\|ERROR" sim_output.log; then
                echo "❌ Test bench execution failed"
                cat sim_output.log
                return 1
            elif grep -q "passed!" sim_output.log; then
                echo "✅ All test benches passed successfully"
                grep "passed!" sim_output.log
            else
                echo "⚠️ Test benches ran but no clear pass/fail indication found"
                cat sim_output.log
            fi
        else
            echo "❌ Test bench execution failed with exit code $?"
            return 1
        fi
    else
        echo "ℹ️ No test benches found for project $project"
    fi
    
    echo "✅ Project $project passed all checks!"
    return 0
}

# Function to display test summary
# Arguments:
#   $1 - array of passed projects (as string)
#   $2 - array of failed projects (as string)
# Returns:
#   0 if all passed, 1 if any failed
display_summary() {
    local passed_projects=($1)
    local failed_projects=($2)
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📊 Test Summary"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    if [ ${#passed_projects[@]} -gt 0 ]; then
        echo "✅ Passed (${#passed_projects[@]}): ${passed_projects[*]}"
    fi
    
    if [ ${#failed_projects[@]} -gt 0 ]; then
        echo "❌ Failed (${#failed_projects[@]}): ${failed_projects[*]}"
        return 1
    else
        echo "🎉 All projects passed!"
        return 0
    fi
}