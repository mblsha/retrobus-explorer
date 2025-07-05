#!/bin/bash
set -e

# FuseSOC setup script for CI
# This script initializes FuseSOC and validates the project configuration

echo "=== Setting up FuseSOC for CI ==="

# Check if we're in the right directory
if [ ! -d "gateware/fusesoc" ]; then
    echo "Error: Must be run from project root directory"
    exit 1
fi

cd gateware/fusesoc

# Initialize FuseSOC workspace
echo "Initializing FuseSOC workspace..."
fusesoc init

# Add the retrobus library
echo "Adding retrobus library..."
fusesoc library add retrobus .

# Validate that FuseSOC can find our configuration
echo "Validating FuseSOC configuration..."
if [ -f "fusesoc.conf" ]; then
    echo "✓ FuseSOC configuration file found"
    cat fusesoc.conf
else
    echo "⚠ No FuseSOC configuration file found"
fi

# List available libraries
echo "Available libraries:"
fusesoc library list

# List available cores
echo "Available cores:"
fusesoc core list

echo "=== FuseSOC setup complete ==="