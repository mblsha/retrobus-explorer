#!/bin/bash
set -euo pipefail

# Script to install Alchitry Labs V2
# This script downloads, extracts, and verifies the Alchitry Labs V2 installation

echo "🔧 Installing Alchitry Labs V2..."

# Get the latest version if not provided
if [ -z "$ALCHITRY_VERSION" ]; then
    echo "📡 Fetching latest Alchitry Labs version..."
    LATEST_VERSION=$(
        curl -fsSL -o /dev/null -w '%{url_effective}' \
            https://github.com/alchitry/Alchitry-Labs-V2/releases/latest \
        | sed -nE 's#^.*/releases/tag/([^/?#]+).*$#\1#p'
    )
    if [ -z "$LATEST_VERSION" ]; then
        LATEST_VERSION=$(curl -fsSL https://api.github.com/repos/alchitry/Alchitry-Labs-V2/releases/latest | sed -nE 's/.*"tag_name":[[:space:]]*"([^"]+)".*/\1/p')
    fi
    if [ -z "$LATEST_VERSION" ]; then
        echo "❌ Failed to resolve latest Alchitry Labs release tag"
        exit 1
    fi
    export ALCHITRY_VERSION="$LATEST_VERSION"
fi

echo "📦 Installing Alchitry Labs V2 version: $ALCHITRY_VERSION"

# Check if already cached
if [ -d "$HOME/alchitry-labs/alchitry-labs-${ALCHITRY_VERSION}" ]; then
    echo "✅ Alchitry Labs already cached, skipping download"
else
    # Create installation directory
    mkdir -p $HOME/alchitry-labs
    cd $HOME/alchitry-labs
    
    # Download the latest Alchitry Labs V2 tar.gz package
    echo "⬇️  Downloading Alchitry Labs V2..."
    wget -q "https://github.com/alchitry/Alchitry-Labs-V2/releases/download/${ALCHITRY_VERSION}/alchitry-labs-${ALCHITRY_VERSION}-linux-amd64.tar.gz"
    
    # Extract the tar.gz package
    echo "📂 Extracting Alchitry Labs V2..."
    tar -xzf "alchitry-labs-${ALCHITRY_VERSION}-linux-amd64.tar.gz"
    
    # Clean up archive
    rm "alchitry-labs-${ALCHITRY_VERSION}-linux-amd64.tar.gz"
fi

# Debug: List the extracted contents to understand the structure
echo "📋 Contents of extracted directory:"
ls -la "$HOME/alchitry-labs/alchitry-labs-${ALCHITRY_VERSION}/" || echo "Directory not found, listing parent:"
ls -la "$HOME/alchitry-labs/"

# Find the actual binary location
echo "🔍 Looking for alchitry binary:"
find "$HOME/alchitry-labs/" -name "alchitry*" -type f 2>/dev/null || echo "No alchitry binary found"

# Verify installation
echo "✅ Verifying Alchitry Labs installation..."

# Find the alchitry binary
ALCHITRY_BIN=$(find "$HOME/alchitry-labs/" -name "alchitry" -type f 2>/dev/null | head -1)

if [ -z "$ALCHITRY_BIN" ]; then
    echo "❌ Could not find alchitry binary"
    exit 1
fi

echo "🎯 Found alchitry binary at: $ALCHITRY_BIN"
chmod +x "$ALCHITRY_BIN"

# Export environment variables for subsequent steps (only in GitHub Actions)
if [ -n "$GITHUB_ENV" ]; then
    echo "ALCHITRY_VERSION=${ALCHITRY_VERSION}" >> $GITHUB_ENV
    echo "ALCHITRY_BIN=$ALCHITRY_BIN" >> $GITHUB_ENV
    echo "📝 Environment variables exported to GitHub Actions"
else
    echo "📝 Environment variables (local execution):"
    echo "   ALCHITRY_VERSION=${ALCHITRY_VERSION}"
    echo "   ALCHITRY_BIN=$ALCHITRY_BIN"
fi

# Test the binary
echo "🧪 Testing alchitry binary..."
"$ALCHITRY_BIN" --help || echo "Binary found but help command failed"

echo "🎉 Alchitry Labs V2 installation completed successfully!"
