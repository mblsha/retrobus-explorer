#!/bin/bash
set -e

# Chisel test runner script for CI
# Usage: ./run-chisel-tests.sh [project] [test-class]

PROJECT=${1:-"pinTester"}
TEST_CLASS=${2:-"retrobus.projects.pin_tester.PinTesterTestSuite"}

echo "=== Running Chisel Tests ==="
echo "Project: $PROJECT"
echo "Test Class: $TEST_CLASS"
echo ""

# Check if we're in the right directory
if [ ! -d "gateware/chisel" ]; then
    echo "Error: Must be run from project root directory"
    exit 1
fi

cd gateware/chisel

# Check if the project exists
if ! sbt "project $PROJECT" "show name" >/dev/null 2>&1; then
    echo "Error: Project '$PROJECT' not found"
    echo "Available projects:"
    sbt "projects"
    exit 1
fi

# Run compilation first
echo "Compiling project..."
sbt "project $PROJECT" compile

# Run the specific test class
echo "Running tests for $TEST_CLASS..."
if sbt "project $PROJECT" "testOnly $TEST_CLASS"; then
    echo "✅ Tests passed for $PROJECT::$TEST_CLASS"
else
    echo "❌ Tests failed for $PROJECT::$TEST_CLASS"
    exit 1
fi

# Check for generated artifacts
if [ -d "test_run_dir" ]; then
    echo "📊 Test artifacts generated:"
    find test_run_dir -name "*.vcd" -exec echo "  - {}" \;
fi

echo "=== Chisel tests complete ==="