#!/usr/bin/env python3
"""
Generic FuseSoC-based build system for RetroBus Explorer
Handles WSL/Windows Vivado integration with proper logging and environment isolation
"""

import os
import sys
import logging
import subprocess
import shutil
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, List, Tuple
import time
import argparse

# Project configurations - centralized project information
PROJECT_CONFIGS = {
    "pin-tester": {
        "sbt_target": "pinTester/runMain retrobus.projects.pin_tester.PinTesterBidirectionalVerilog",
        "fusesoc_core": "retrobus:projects:pin_tester",
        "description": "Hardware verification tool for testing all FPGA pins",
        "long_description": "Comprehensive hardware verification tool that tests all 48 FPGA pins through the level shifter interface. Includes bidirectional pin support using Xilinx IOBUF primitives."
    },
    "sharp-organizer-card": {
        "sbt_target": "sharpOrganizerCard/run", 
        "fusesoc_core": "retrobus:projects:sharp_organizer_card",
        "description": "Interface for Sharp electronic organizers",
        "long_description": "FPGA interface for capturing and analyzing signals from Sharp pocket computers and electronic organizers. Supports Z80 bus analysis and LCD/keyboard decoding."
    }
}

def get_project_list() -> List[str]:
    """Get list of available project names"""
    return list(PROJECT_CONFIGS.keys())

def get_project_info(project_name: str) -> Optional[Dict]:
    """Get project configuration info"""
    return PROJECT_CONFIGS.get(project_name)

def print_available_projects():
    """Print formatted list of available projects"""
    print("Available projects:")
    for name, config in PROJECT_CONFIGS.items():
        print(f"  {name:<20} - {config['description']}")

def validate_project_name(project_name: str) -> bool:
    """Validate that project name exists in configuration"""
    return project_name in PROJECT_CONFIGS

# Configure logging
def setup_logging(project_name: str, log_level: str = "INFO") -> logging.Logger:
    """Set up logging with both file and console output"""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"fusesoc_{project_name}_{timestamp}.log"
    
    # Create logger
    logger = logging.getLogger(f"fusesoc_{project_name}")
    logger.setLevel(logging.DEBUG)  # Always capture everything
    
    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # File handler (captures everything)
    fh = logging.FileHandler(log_file)
    fh.setLevel(logging.DEBUG)
    
    # Console handler (configurable level)
    ch = logging.StreamHandler()
    ch.setLevel(getattr(logging, log_level.upper()))
    
    # Formatter with more detail for file
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
    )
    simple_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    fh.setFormatter(detailed_formatter)
    ch.setFormatter(simple_formatter)
    
    logger.addHandler(fh)
    logger.addHandler(ch)
    
    logger.info(f"Logging to: {log_file}")
    return logger

def load_env_config(env_file: str = ".env") -> Dict[str, str]:
    """Load environment configuration from .env file"""
    config = {}
    env_path = Path(env_file)
    
    if not env_path.exists():
        raise FileNotFoundError(
            f"{env_file} not found. Please copy .env.example to .env and configure it."
        )
    
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip()
    
    # Set defaults
    config.setdefault('LOG_LEVEL', 'INFO')
    config.setdefault('BUILD_ROOT', 'build_fusesoc')
    config.setdefault('FUSESOC_CACHE', '.fusesoc_cache')
    config.setdefault('VIVADO_JOBS', '8')
    
    return config

def create_vivado_wrapper(config: Dict[str, str], logger: logging.Logger) -> Path:
    """Create a Vivado wrapper script for WSL/Windows integration"""
    wrapper_path = Path("vivado_wsl_wrapper.py")
    
    wrapper_content = f'''#!/usr/bin/env python3
import sys
import subprocess
import os
import re
from datetime import datetime
from pathlib import Path

def wsl_to_windows_path(path):
    """Convert WSL path to Windows path"""
    if path.startswith("/mnt/c/"):
        return path.replace("/mnt/c/", "C:/").replace("/", "/")
    elif path.startswith("/mnt/d/"):
        return path.replace("/mnt/d/", "D:/").replace("/", "/")
    return path

def main():
    vivado_path = r"{config['VIVADO_WIN_PATH']}\\bin\\vivado.bat"
    
    # Log the command being executed with timestamp
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    with open(log_dir / "vivado_calls.log", "a") as log:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log.write(f"\\n[{{timestamp}}] Vivado wrapper called with args: {{sys.argv}}\\n")
    
    # Skip the first argument if it's 'vivado' (compatibility with EDALIZE_LAUNCHER)
    args_to_process = sys.argv[1:]
    if args_to_process and args_to_process[0] == 'vivado':
        args_to_process = args_to_process[1:]
        with open(log_dir / "vivado_calls.log", "a") as log:
            log.write(f"  Skipping redundant 'vivado' argument\\n")
    
    # Convert paths in arguments
    args = []
    for arg in args_to_process:
        if arg.startswith("/") and "/mnt/" in arg:
            converted = wsl_to_windows_path(arg)
            args.append(converted)
            with open(log_dir / "vivado_calls.log", "a") as log:
                log.write(f"  Path converted: {{arg}} -> {{converted}}\\n")
        else:
            args.append(arg)
    
    # Build the command
    cmd = f'cmd.exe /c "{{vivado_path}}" {{" ".join(args)}}'
    
    with open(log_dir / "vivado_calls.log", "a") as log:
        log.write(f"  Full command: {{cmd}}\\n")
    
    # Execute
    result = subprocess.run(cmd, shell=True, capture_output=False)
    
    with open(log_dir / "vivado_calls.log", "a") as log:
        log.write(f"  Exit code: {{result.returncode}}\\n")
    
    sys.exit(result.returncode)

if __name__ == "__main__":
    main()
'''
    
    with open(wrapper_path, 'w') as f:
        f.write(wrapper_content)
    
    os.chmod(wrapper_path, 0o755)
    logger.info(f"Created Vivado wrapper at: {wrapper_path}")
    return wrapper_path

def create_fusesoc_config(config: Dict[str, str], wrapper_path: Path, logger: logging.Logger) -> Path:
    """Create FuseSoC configuration file"""
    fusesoc_config = f"""[main]
build_root = {config['BUILD_ROOT']}
cache_root = {config['FUSESOC_CACHE']}
library_root = libraries

[library.retrobus]
location = gateware/chisel/cores
sync-uri = gateware/chisel/cores
sync-type = local
auto-sync = true

[tool.vivado]
path = {wrapper_path.absolute()}
jobs = {config['VIVADO_JOBS']}
"""

    config_path = Path("fusesoc_config.conf")
    with open(config_path, 'w') as f:
        f.write(fusesoc_config)
    
    logger.info(f"Created FuseSoC config at: {config_path}")
    logger.debug(f"Config contents:\n{fusesoc_config}")
    return config_path

def run_command_with_logging(cmd: List[str], cwd: Path, logger: logging.Logger, description: str) -> subprocess.CompletedProcess:
    """Run a command with detailed logging"""
    logger.info(f"{description}: {' '.join(cmd)}")
    logger.debug(f"Working directory: {cwd}")
    
    start_time = time.time()
    
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True
        )
        
        elapsed = time.time() - start_time
        logger.info(f"{description} completed in {elapsed:.1f}s (exit code: {result.returncode})")
        
        if result.stdout:
            logger.debug(f"STDOUT:\n{result.stdout}")
        if result.stderr:
            logger.warning(f"STDERR:\n{result.stderr}")
            
        return result
        
    except Exception as e:
        logger.error(f"{description} failed with exception: {e}")
        raise

def run_chisel_build(project_name: str, sbt_target: str, logger: logging.Logger) -> bool:
    """Run Chisel build to generate SystemVerilog"""
    logger.info("="*60)
    logger.info(f"Starting Chisel build for {project_name}")
    logger.info("="*60)
    
    try:
        # Check if we're in WSL
        if not Path("/mnt/c").exists():
            logger.error("This script must be run from WSL")
            return False
        
        # Change to Chisel directory
        chisel_dir = Path("gateware/chisel")
        if not chisel_dir.exists():
            logger.error(f"Chisel directory not found: {chisel_dir}")
            return False
        
        # Check for build.sbt
        build_sbt = chisel_dir / "build.sbt"
        if not build_sbt.exists():
            logger.error(f"build.sbt not found at: {build_sbt}")
            return False
        
        logger.info(f"Found build.sbt at: {build_sbt}")
        
        # Run SBT build
        logger.info(f"Generating SystemVerilog with SBT target: {sbt_target}")
        result = run_command_with_logging(
            ["sbt", sbt_target],
            chisel_dir,
            logger,
            "SBT build"
        )
        
        if result.returncode != 0:
            logger.error(f"SBT build failed with exit code: {result.returncode}")
            return False
        
        # Look for generated files
        logger.info("Looking for generated SystemVerilog files...")
        generated_dir = chisel_dir / "generated"
        
        # For pin-tester, check if the generated files exist
        if project_name == "pin-tester":
            expected_files = [
                generated_dir / "PinTesterBidirectional.sv",
                generated_dir / "IOBUFGenerator.v"
            ]
            for expected_file in expected_files:
                if not expected_file.exists():
                    logger.error(f"Expected file not found: {expected_file}")
                    return False
                logger.info(f"Found generated file: {expected_file}")
        else:
            # For other projects, use the old logic of copying files
            sv_files = []
            for pattern in ["*.sv", "generated/*.sv"]:
                for sv_file in chisel_dir.glob(pattern):
                    sv_files.append(sv_file)
                    logger.info(f"Found generated file: {sv_file}")
            
            if not sv_files:
                logger.error("No SystemVerilog files generated!")
                return False
            
            # Copy generated files to cores directory
            cores_dir = chisel_dir / "cores"
            cores_dir.mkdir(exist_ok=True)
            
            for sv_file in sv_files:
                dest = cores_dir / sv_file.name
                shutil.copy2(sv_file, dest)
                logger.info(f"Copied: {sv_file.name} -> {dest}")
        
        logger.info("Chisel build completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Chisel build failed with exception: {e}", exc_info=True)
        return False

def run_fusesoc_build(project_name: str, fusesoc_core: str, config: Dict[str, str], config_path: Path, wrapper_path: Path, logger: logging.Logger) -> bool:
    """Run FuseSoC build"""
    logger.info("="*60)
    logger.info(f"Starting FuseSoC build for {project_name}")
    logger.info("="*60)
    
    try:
        # Set environment
        env = os.environ.copy()
        env['FUSESOC_CONFIG'] = str(config_path)
        # Set EDALIZE_LAUNCHER to use our wrapper
        env['EDALIZE_LAUNCHER'] = f"python3 {wrapper_path.absolute()}"
        
        # First, update the library
        logger.info("Updating FuseSoC library...")
        update_cmd = ["fusesoc", "library", "update"]
        update_result = subprocess.run(update_cmd, env=env, capture_output=True, text=True)
        
        if update_result.returncode != 0:
            logger.warning(f"Library update warning: {update_result.stderr}")
        
        # List available cores
        logger.info("Listing available cores...")
        list_cmd = ["fusesoc", "core", "list"]
        list_result = subprocess.run(list_cmd, env=env, capture_output=True, text=True)
        
        if list_result.returncode == 0:
            cores = [line for line in list_result.stdout.split('\n') if 'retrobus' in line]
            logger.info(f"Available retrobus cores: {cores}")
        
        # Build command
        cmd = [
            "fusesoc",
            "--verbose" if config.get('LOG_LEVEL') == 'DEBUG' else "",
            "run",
            "--tool=vivado",
            "--target=default",
            fusesoc_core
        ]
        
        # Remove empty strings from command
        cmd = [c for c in cmd if c]
        
        logger.info(f"Running FuseSoC: {' '.join(cmd)}")
        
        # Run FuseSoC with real-time output
        process = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        # Stream output
        output_lines = []
        for line in process.stdout:
            line = line.rstrip()
            if line:
                output_lines.append(line)
                # Log different types of messages with appropriate levels
                if "ERROR" in line or "CRITICAL" in line:
                    logger.error(f"FuseSoC: {line}")
                elif "WARNING" in line:
                    logger.warning(f"FuseSoC: {line}")
                else:
                    logger.info(f"FuseSoC: {line}")
        
        process.wait()
        
        if process.returncode != 0:
            logger.error(f"FuseSoC build failed with code: {process.returncode}")
            # Save full output to a file for debugging
            error_log = Path("logs") / f"fusesoc_error_{project_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            with open(error_log, 'w') as f:
                f.write('\n'.join(output_lines))
            logger.error(f"Full output saved to: {error_log}")
            return False
        
        logger.info("FuseSoC build completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"FuseSoC build failed with exception: {e}", exc_info=True)
        return False

def find_bitstream(project_name: str, config: Dict[str, str], logger: logging.Logger) -> List[Path]:
    """Find generated bitstream files"""
    logger.info("Looking for generated bitstream...")
    
    # Convert project name to core name format (e.g., pin-tester -> pin_tester)
    core_name = project_name.replace("-", "_")
    
    # Try various patterns
    patterns = [
        f"build/retrobus_projects_{core_name}_*/default-vivado/retrobus_projects_{core_name}_*.runs/impl_1/*.bit",
        f"{config['BUILD_ROOT']}/retrobus_projects_{core_name}_*/default-vivado/*.bit",
        f"{config['BUILD_ROOT']}/retrobus_projects_{core_name}_*/**/*.bit",
        f"{config['BUILD_ROOT']}/retrobus_{core_name}_*/vivado/*.bit",
        f"{config['BUILD_ROOT']}/**/{core_name}*.bit",
        f"{config['BUILD_ROOT']}/**/*.bit"
    ]
    
    bitstreams = []
    for pattern in patterns:
        bitstreams = list(Path(".").glob(pattern))
        if bitstreams:
            logger.info(f"Found bitstream(s) with pattern: {pattern}")
            break
    
    return bitstreams

def copy_bitstream_to_local(project_name: str, config: Dict[str, str], logger: logging.Logger) -> Optional[Path]:
    """Find and copy bitstream to local directory with timestamp"""
    # First try to find in the standard build directory structure
    bitstreams = find_bitstream(project_name, config, logger)
    
    # If not found in build_fusesoc, check the build directory
    if not bitstreams:
        logger.info("Checking alternative build directory...")
        core_name = project_name.replace("-", "_")
        alt_pattern = f"build/retrobus_projects_{core_name}_*/default-vivado/retrobus_projects_{core_name}_*.runs/impl_1/*.bit"
        bitstreams = list(Path(".").glob(alt_pattern))
        if bitstreams:
            logger.info(f"Found bitstream in build directory: {bitstreams[0]}")
    
    if not bitstreams:
        logger.error("No bitstream found!")
        logger.error("Searched patterns:")
        logger.error(f"  - build_fusesoc/**/*.bit")
        logger.error(f"  - build/**/*.bit")
        return None
    
    # Use the first (usually only) bitstream found
    source_bitstream = bitstreams[0]
    logger.info(f"Found bitstream: {source_bitstream}")
    
    # Create output directory
    output_dir = Path("bitstreams")
    output_dir.mkdir(exist_ok=True)
    
    # Copy with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = project_name.replace("-", "_")
    dest_name = f"{safe_name}_{timestamp}.bit"
    dest_path = output_dir / dest_name
    
    shutil.copy2(source_bitstream, dest_path)
    logger.info(f"Copied bitstream to: {dest_path}")
    
    # Also copy to a "latest" file for convenience
    latest_path = output_dir / f"{safe_name}_latest.bit"
    shutil.copy2(source_bitstream, latest_path)
    logger.info(f"Also copied as: {latest_path}")
    
    # Log file size
    size_mb = dest_path.stat().st_size / (1024 * 1024)
    logger.info(f"Bitstream size: {size_mb:.2f} MB")
    
    return dest_path

def main():
    """Main build process"""
    # Handle special command line options
    if len(sys.argv) >= 2:
        if sys.argv[1] == "--list-projects":
            print_available_projects()
            sys.exit(0)
        elif sys.argv[1] == "--validate-project" and len(sys.argv) >= 3:
            project_name = sys.argv[2]
            if validate_project_name(project_name):
                sys.exit(0)  # Valid project
            else:
                sys.exit(1)  # Invalid project
    
    # Parse command line arguments for build
    if len(sys.argv) < 2:
        print("Error: No project name provided")
        print(f"Usage: {sys.argv[0]} <project_name>")
        print()
        print_available_projects()
        sys.exit(1)
    
    project_name = sys.argv[1]
    
    # Validate project name
    if not validate_project_name(project_name):
        print(f"Error: Unknown project '{project_name}'")
        print()
        print_available_projects()
        sys.exit(1)
    
    project_config = get_project_info(project_name)
    
    print("\n" + "="*60)
    print(f"RetroBus {project_config['description']} FuseSoC Build")
    print("="*60 + "\n")
    
    # Load configuration
    try:
        config = load_env_config()
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    
    # Set up logging
    logger = setup_logging(project_name, config.get('LOG_LEVEL', 'INFO'))
    logger.info(f"Starting FuseSoC build process for {project_name}")
    
    # Log configuration (without sensitive paths at INFO level)
    logger.info(f"Configuration loaded: {len(config)} settings")
    logger.info(f"Build root: {config['BUILD_ROOT']}")
    logger.info(f"Log level: {config.get('LOG_LEVEL', 'INFO')}")
    logger.info(f"SBT target: {project_config['sbt_target']}")
    logger.info(f"FuseSoC core: {project_config['fusesoc_core']}")
    
    # Log all config at DEBUG level
    for key, value in config.items():
        logger.debug(f"Config: {key} = {value}")
    
    # Create build directories
    for dir_name in [config['BUILD_ROOT'], config['FUSESOC_CACHE'], 'logs', 'bitstreams']:
        Path(dir_name).mkdir(exist_ok=True)
        logger.debug(f"Created directory: {dir_name}")
    
    # Track overall timing
    start_time = time.time()
    
    # Step 1: Create Vivado wrapper
    logger.info("\nStep 1/4: Creating Vivado wrapper...")
    wrapper_path = create_vivado_wrapper(config, logger)
    
    # Step 2: Create FuseSoC configuration
    logger.info("\nStep 2/4: Creating FuseSoC configuration...")
    fusesoc_config_path = create_fusesoc_config(config, wrapper_path, logger)
    
    # Step 3: Run Chisel build
    logger.info("\nStep 3/4: Running Chisel build...")
    if not run_chisel_build(project_name, project_config['sbt_target'], logger):
        logger.error(f"\nBUILD FAILED at Chisel generation step for {project_name}")
        logger.error("Check logs directory for detailed error information")
        sys.exit(1)
    
    # Step 4: Run FuseSoC build
    logger.info("\nStep 4/4: Running FuseSoC synthesis...")
    if not run_fusesoc_build(project_name, project_config['fusesoc_core'], config, fusesoc_config_path, wrapper_path, logger):
        logger.error(f"\nBUILD FAILED at FuseSoC synthesis step for {project_name}")
        logger.error("Check logs directory for detailed error information")
        sys.exit(1)
    
    # Copy bitstream
    logger.info("\nCopying bitstream to local directory...")
    bitstream_path = copy_bitstream_to_local(project_name, config, logger)
    
    # Summary
    elapsed = time.time() - start_time
    logger.info("\n" + "="*60)
    logger.info("BUILD COMPLETED SUCCESSFULLY!")
    logger.info(f"Project: {project_name} ({project_config['description']})")
    logger.info(f"Total build time: {elapsed/60:.1f} minutes")
    logger.info(f"Logs available in: logs/")
    if bitstream_path:
        safe_name = project_name.replace("-", "_")
        logger.info(f"Bitstream copied to: {bitstream_path}")
        logger.info(f"Latest bitstream: bitstreams/{safe_name}_latest.bit")
    logger.info("="*60 + "\n")

if __name__ == "__main__":
    main()