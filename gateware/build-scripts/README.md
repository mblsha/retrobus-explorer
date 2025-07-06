# FuseSoC Build System for RetroBus Explorer

This directory contains a comprehensive FuseSoC-based build system for building FPGA designs on Windows using WSL.

## Quick Start

From the repository root:

```bash
# Copy and configure environment
cp .env.example .env
nano .env  # Set your Vivado paths

# Build any project
./gateware/build-scripts/build_fusesoc.sh <project-name>

# Examples
./gateware/build-scripts/build_fusesoc.sh pin-tester
./gateware/build-scripts/build_fusesoc.sh sharp-organizer-card
```

## Available Projects

- **pin-tester** - Hardware verification tool for testing all FPGA pins
- **sharp-organizer-card** - Interface for Sharp electronic organizers

## Directory Structure

```
build-scripts/
├── build_fusesoc.sh         # Generic build script (main entry point)
├── build_local.sh          # Local build wrapper (runs on Windows via SSH)
├── fusesoc_build.py         # Python build orchestrator
├── build_pin_tester.sh      # Convenience wrapper for pin-tester
└── README.md                # This file
```

## Build System Overview

The build system maximizes FuseSoC usage while:
- Keeping sensitive paths in `.env` configuration (not committed to git)
- Providing comprehensive logging of all build actions
- Seamlessly integrating WSL and Windows Vivado
- Automating the entire build flow from Chisel to bitstream
- Supporting both local and remote builds

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Chisel    │────▶│    FuseSoC   │────▶│   Vivado    │
│    (WSL)    │     │    (WSL)     │     │  (Windows)  │
└─────────────┘     └──────────────┘     └─────────────┘
       │                    │                     │
       ▼                    ▼                     ▼
   [*.scala]           [*.core]              [*.bit]
                           │
                           ▼
                    [fusesoc_config.conf]
                    [vivado_wrapper.py]
```

## Initial Setup

### 1. Clone Repository (Windows)

```cmd
cd C:\Users\username\src
git clone https://github.com/mblsha/retrobus-explorer.git
```

### 2. Install WSL Prerequisites

```bash
# Install Java and Python dependencies
sudo apt-get update
sudo apt-get install openjdk-11-jdk python3-pip

# For SBT installation instructions, see the build script output when SBT is missing
# The build script will provide the exact commands needed for your system
```

### 3. Set up Python Environment

```bash
# In fish shell
fish
cd $WINDOWS_PROJECT_PATH
pyenv virtualenv 3.10.11 fusesoc
pyenv local fusesoc
python -m pip install fusesoc
```

### 4. Configure Environment

```bash
# Copy the example configuration
cp .env.example .env

# Edit with your system paths - all variables are documented in .env.example
nano .env
```

## Build Process

The build system performs these steps:

1. **Environment Setup** - Loads configuration from `.env`, creates timestamped log file
2. **Vivado Wrapper Creation** - Generates wrapper handling WSL→Windows path translation
3. **FuseSoC Configuration** - Creates config pointing to Vivado wrapper
4. **Chisel Build** - Runs SBT to generate SystemVerilog
5. **FuseSoC Synthesis** - Runs FuseSoC with Vivado backend
6. **Bitstream Collection** - Copies bitstream to `bitstreams/` directory

## Output Locations

All paths are relative to repository root:
- **Bitstreams**: 
  - `bitstreams/<project>_latest.bit` - Most recent build
  - `bitstreams/<project>_YYYYMMDD_HHMMSS.bit` - Timestamped versions
- **Build logs**: `logs/fusesoc_<project>_YYYYMMDD_HHMMSS.log`
- **Vivado logs**: `logs/vivado_calls.log`
- **Build artifacts**: `build_fusesoc/<core_name>_*/`

## Build Options

```bash
# Build with debug logging
LOG_LEVEL=DEBUG ./gateware/build-scripts/build_fusesoc.sh pin-tester

# Build specific project
./gateware/build-scripts/build_fusesoc.sh sharp-organizer-card

# Use convenience wrapper
./gateware/build-scripts/build_pin_tester.sh
```

## Remote Builds

For distributed builds or when running from a different machine:

```bash
# Configure SSH/SCP settings in .env (see .env.example for documentation)
# Then run remote build
./gateware/build-scripts/build_local.sh pin-tester
```

## Adding New Projects

To add a new project:

1. Create Chisel project in `gateware/chisel/projects/<name>/`
2. Add SBT configuration to `gateware/chisel/build.sbt`
3. Create FuseSoC core file in `gateware/chisel/cores/`
   - Specify the FPGA part in the core file's `tools.vivado.part` field
   - This allows different projects to target different FPGA boards
4. Edit `fusesoc_build.py` and add to `PROJECT_CONFIGS`:
   ```python
   "your-project": {
       "sbt_target": "yourProject/run",
       "fusesoc_core": "retrobus:projects:your_project",
       "description": "Your project description"
   }
   ```

## Troubleshooting

### "FuseSoC not found"
```bash
python3 -m pip install fusesoc
```

### "SBT not found"
Run the build script - it will display the exact SBT installation commands for your system.

### "Core not found"
```bash
# Update FuseSoC library
fusesoc library update

# List available cores
fusesoc core list | grep retrobus
```

### Path not found errors
Check your `.env` file - ensure all paths use appropriate format:
- Windows paths: `C:\Path\To\Vivado`
- WSL paths: `/mnt/c/Path/To/Vivado`

### Vivado license errors
Ensure Vivado can find its license when called from WSL:
```bash
export XILINXD_LICENSE_FILE=/mnt/c/path/to/license.lic
```

## Logging

The system provides multiple levels of logging:
- **Console output**: Configured by `LOG_LEVEL` in `.env`
- **File logs**: Always capture DEBUG level (in `logs/`)
- **Vivado calls**: Logged to `logs/vivado_calls.log`

Log levels: `ERROR`, `WARNING`, `INFO` (default), `DEBUG`

## Advanced Usage

### Custom Build Targets
To use different FuseSoC targets (e.g., simulation vs synthesis):
```bash
# Modify the Python script or pass as parameter
./build_fusesoc.sh project_name --target=sim
```

### Parallel Builds
Adjust `VIVADO_JOBS` in `.env` to control synthesis parallelism.

### CI/CD Integration
The build scripts can be called from CI systems:
```python
import subprocess
subprocess.run(["./gateware/build-scripts/build_fusesoc.sh", "pin-tester"])
```

## Security Notes

- The `.env` file contains system-specific paths and is excluded from git
- All build actions are logged for audit purposes
- Sensitive paths are not logged at INFO level
- The wrapper scripts are generated dynamically and excluded from git

## Example: Building Pin-Tester

```bash
# One-time setup
cd $WINDOWS_PROJECT_PATH  # Set in .env file
cp .env.example .env
nano .env  # Configure your paths

# Build the project
./gateware/build-scripts/build_fusesoc.sh pin-tester

# Check the results
ls -la bitstreams/pin_tester_latest.bit
tail logs/fusesoc_pin_tester_*.log
```

The bitstream will be available at `bitstreams/pin_tester_latest.bit`.