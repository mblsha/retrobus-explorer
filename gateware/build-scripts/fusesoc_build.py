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
        "additional_targets": ["pinTester/runMain retrobus.projects.pin_tester.PinTesterTopVerilog"],
        "fusesoc_core": "retrobus:projects:pin_tester",
        "description": "Hardware verification tool for testing all FPGA pins",
        "long_description": "Comprehensive hardware verification tool that tests all 48 FPGA pins through the level shifter interface. Includes bidirectional pin support using Xilinx IOBUF primitives."
    },
    "sharp-organizer-card": {
        "sbt_target": "sharpOrganizerCard/runMain retrobus.projects.sharp_organizer_card.SharpOrganizerCardTop", 
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
    
    # If .env not found locally, try parent directory (for remote builds)
    if not env_path.exists():
        parent_env = Path("..") / env_file
        if parent_env.exists():
            env_path = parent_env
        else:
            # Try going up more levels to find the .env file at repository root
            repo_root_env = Path("../..") / env_file
            if repo_root_env.exists():
                env_path = repo_root_env
            else:
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
import shutil
import tempfile
import re
from datetime import datetime
from pathlib import Path

def create_windows_workspace():
    """Create a Windows-accessible workspace and copy necessary files"""
    # Create a temporary directory in C:\\temp that Windows can access
    windows_temp = Path("/mnt/c/temp")
    windows_temp.mkdir(exist_ok=True)
    
    # Create unique workspace directory
    workspace_name = "vivado_" + str(os.getpid()) + "_" + str(int(datetime.now().timestamp()))
    workspace_path = windows_temp / workspace_name
    workspace_path.mkdir(exist_ok=True)
    
    # Copy current directory contents to Windows workspace
    cwd = Path(os.getcwd())
    
    # Copy essential files for Vivado
    patterns_to_copy = ["*.tcl", "*.xpr", "*.sv", "*.v", "*.xdc", "*.txt", "*.prj", "*.xci", "Makefile", "*.yml", "*.eda"]
    copied_files = []
    
    for pattern in patterns_to_copy:
        for file_path in cwd.glob(pattern):
            if file_path.is_file():
                dest_path = workspace_path / file_path.name
                shutil.copy2(file_path, dest_path)
                copied_files.append(file_path.name)
    
    # Also copy any subdirectories that might contain source files
    for subdir in cwd.iterdir():
        if subdir.is_dir() and subdir.name in ["src", "sources", "hdl", "rtl", "constraints"]:
            dest_subdir = workspace_path / subdir.name
            shutil.copytree(subdir, dest_subdir, dirs_exist_ok=True)
            copied_files.append(subdir.name + "/")
    
    # Copy Chisel generated files if they exist
    # Look for chisel directory in current dir or parent directories
    chisel_dir = None
    search_path = cwd
    for _ in range(4):  # Search up to 4 levels up
        potential_chisel = search_path / "chisel"
        if potential_chisel.exists():
            chisel_dir = potential_chisel
            break
        # Also check for gateware/chisel if we're at repository root
        potential_gateware_chisel = search_path / "gateware" / "chisel"
        if potential_gateware_chisel.exists():
            chisel_dir = potential_gateware_chisel
            break
        search_path = search_path.parent
    
    if chisel_dir:
        # Copy specific Chisel subdirectories that Vivado needs
        for chisel_subdir in ["cores", "generated", "constraints"]:
            chisel_src = chisel_dir / chisel_subdir
            if chisel_src.exists():
                # Copy to both chisel/ location and also to the path structure expected by TCL
                dest_chisel_subdir = workspace_path / "chisel" / chisel_subdir
                dest_chisel_subdir.parent.mkdir(exist_ok=True)
                shutil.copytree(chisel_src, dest_chisel_subdir, dirs_exist_ok=True)
                copied_files.append("chisel/" + chisel_subdir + "/")
                
                # Also copy to the structure expected by the TCL files
                # TCL expects paths like src/retrobus_projects_pin_tester_1.0.0/../generated/
                # So we create a symlink or copy at the expected location
                src_project_dir = workspace_path / "src" / "retrobus_projects_pin_tester_1.0.0"
                src_project_dir.mkdir(parents=True, exist_ok=True)
                dest_expected = src_project_dir.parent / chisel_subdir
                if not dest_expected.exists():
                    shutil.copytree(chisel_src, dest_expected, dirs_exist_ok=True)
                    copied_files.append("src/" + chisel_subdir + "/")
        
        # Copy any loose SystemVerilog files in chisel directory
        for sv_file in chisel_dir.glob("*.sv"):
            dest_sv = workspace_path / "chisel" / sv_file.name
            dest_sv.parent.mkdir(exist_ok=True)
            shutil.copy2(sv_file, dest_sv)
            copied_files.append("chisel/" + sv_file.name)
    
    # Also check for and copy sharp-organizer-card IP cores if they exist
    # This is needed because the core file references IP from another project
    sharp_org_dir = None
    search_path_sharp = cwd
    for _ in range(4):  # Search up to 4 levels up
        potential_sharp_org = search_path_sharp / "sharp-organizer-card"
        if potential_sharp_org.exists():
            sharp_org_dir = potential_sharp_org
            break
        potential_gateware_sharp = search_path_sharp / "gateware" / "sharp-organizer-card"
        if potential_gateware_sharp.exists():
            sharp_org_dir = potential_gateware_sharp
            break
        search_path_sharp = search_path_sharp.parent
    
    if sharp_org_dir:
        # Copy the cores directory which contains the IP
        sharp_cores = sharp_org_dir / "cores"
        if sharp_cores.exists():
            dest_sharp = workspace_path / "sharp-organizer-card" / "cores"
            dest_sharp.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(sharp_cores, dest_sharp, dirs_exist_ok=True)
            copied_files.append("sharp-organizer-card/cores/")
    
    return workspace_path, copied_files

def windows_path(wsl_path):
    """Convert WSL path to Windows path"""
    if isinstance(wsl_path, Path):
        wsl_path = str(wsl_path)
    
    if wsl_path.startswith("/mnt/c/"):
        return wsl_path.replace("/mnt/c/", "C:\\\\").replace("/", "\\\\")
    elif wsl_path.startswith("/mnt/d/"):
        return wsl_path.replace("/mnt/d/", "D:\\\\").replace("/", "\\\\")
    return wsl_path

def main():
    vivado_path = r"{config['VIVADO_WIN_PATH']}\\bin\\vivado.bat"
    
    # Log the command being executed with timestamp
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    with open(log_dir / "vivado_calls.log", "a") as log:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log.write(f"\\n[" + timestamp + "] Vivado wrapper called with args: " + str(sys.argv) + "\\n")
        log.write(f"  Original working directory: " + os.getcwd() + "\\n")
    
    # Create Windows workspace and copy files
    try:
        workspace_path, copied_files = create_windows_workspace()
        windows_workspace = windows_path(workspace_path)
        
        with open(log_dir / "vivado_calls.log", "a") as log:
            log.write(f"  Created Windows workspace: " + windows_workspace + "\\n")
            log.write(f"  Copied " + str(len(copied_files)) + " files/directories: " + ', '.join(copied_files[:10]) + ('...' if len(copied_files) > 10 else '') + "\\n")
        
        # Skip the first argument if it's 'vivado' (compatibility with EDALIZE_LAUNCHER)
        args_to_process = sys.argv[1:]
        if args_to_process and args_to_process[0] == 'vivado':
            args_to_process = args_to_process[1:]
            with open(log_dir / "vivado_calls.log", "a") as log:
                log.write(f"  Skipping redundant 'vivado' argument\\n")
        
        # Process arguments - handle multiple TCL scripts and project files properly
        processed_args = []
        tcl_scripts = []
        project_file = None
        
        i = 0
        while i < len(args_to_process):
            arg = args_to_process[i]
            
            if arg == "-source" and i + 1 < len(args_to_process):
                # Handle -source script pairs
                script = args_to_process[i + 1]
                if script.startswith("./") or script.startswith("../"):
                    script = os.path.basename(script)
                tcl_scripts.append(script)
                i += 2  # Skip both -source and script name
            elif arg.endswith(".xpr"):
                # Project file - should be opened, not passed as argument
                if arg.startswith("./") or arg.startswith("../"):
                    project_file = os.path.basename(arg)
                else:
                    project_file = arg
                i += 1
            elif arg.endswith(".tcl"):
                # TCL script without -source flag
                tcl_scripts.append(os.path.basename(arg) if (arg.startswith("./") or arg.startswith("../")) else arg)
                if arg.startswith("./") or arg.startswith("../"):
                    with open(log_dir / "vivado_calls.log", "a") as log:
                        log.write(f"  Converted relative path: " + arg + " -> " + os.path.basename(arg) + "\\n")
                i += 1
            elif arg.startswith("./") or arg.startswith("../") or (not arg.startswith("-") and "." in arg and "/" in arg):
                # Other relative file paths
                filename = os.path.basename(arg)
                processed_args.append(filename)
                with open(log_dir / "vivado_calls.log", "a") as log:
                    log.write(f"  Converted relative path: " + arg + " -> " + os.path.basename(arg) + "\\n")
                i += 1
            else:
                processed_args.append(arg)
                i += 1
        
        # Build the command to run in Windows workspace
        with open(log_dir / "vivado_calls.log", "a") as log:
            log.write(f"  Working directory: " + windows_workspace + "\\n")
            log.write(f"  Parsed TCL scripts: " + str(tcl_scripts) + "\\n")
            log.write(f"  Project file: " + str(project_file) + "\\n")
            log.write(f"  Other args: " + str(processed_args) + "\\n")
        
        # Handle different Vivado command scenarios
        if project_file and tcl_scripts:
            # Opening project and running scripts - create a combined TCL script
            combined_script = "combined_script.tcl"
            combined_script_path = workspace_path / combined_script
            
            with open(combined_script_path, "w") as f:
                f.write(f"# Combined TCL script generated by Vivado wrapper\\n")
                f.write(f"open_project " + project_file + "\\n")
                for script in tcl_scripts:
                    f.write(f"source " + script + "\\n")
            
            cmd_args = ' '.join(processed_args + ['-source', combined_script])
            
            with open(log_dir / "vivado_calls.log", "a") as log:
                log.write(f"  Created combined script: " + combined_script + "\\n")
        elif project_file:
            # Just opening project
            cmd_args = ' '.join(processed_args + [project_file])
        elif tcl_scripts:
            # Just running scripts
            if len(tcl_scripts) == 1:
                cmd_args = ' '.join(processed_args + ['-source', tcl_scripts[0]])
            else:
                # Multiple scripts - create combined script
                combined_script = "combined_script.tcl"
                combined_script_path = workspace_path / combined_script
                
                with open(combined_script_path, "w") as f:
                    f.write(f"# Combined TCL script generated by Vivado wrapper\\n")
                    for script in tcl_scripts:
                        f.write(f"source " + script + "\\n")
                
                cmd_args = ' '.join(processed_args + ['-source', combined_script])
                
                with open(log_dir / "vivado_calls.log", "a") as log:
                    log.write(f"  Created combined script: " + combined_script + "\\n")
        else:
            # No special handling needed
            cmd_args = ' '.join(processed_args)
        
        cmd = f'cmd.exe /c "' + vivado_path + ' ' + cmd_args + '"'
        
        with open(log_dir / "vivado_calls.log", "a") as log:
            log.write(f"  Final args: " + cmd_args + "\\n")
            log.write(f"  Full command: " + cmd + "\\n")
        
        # Execute Vivado in Windows workspace with detailed output capture
        with open(log_dir / "vivado_calls.log", "a") as log:
            log.write(f"  Executing command...\\n")
        
        # Change to a Windows-accessible directory before running cmd.exe to avoid UNC path issues
        original_cwd = os.getcwd()
        log_file_path = Path(original_cwd) / log_dir / "vivado_calls.log"
        try:
            # Change to the Windows workspace directory in WSL
            os.chdir(workspace_path)
            with open(log_file_path, "a") as log:
                log.write(f"  Changed working directory to: " + str(workspace_path) + "\\n")
            
            # Execute Vivado with real-time output streaming
            print("\\n🔨 Starting Vivado execution - real-time output:")
            print("=" * 60)
            
            stdout_capture = []
            stderr_capture = []
            
            import threading
            
            with subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                                text=True, bufsize=1, universal_newlines=True) as process:
                
                def read_stdout():
                    for line in iter(process.stdout.readline, ''):
                        if line:
                            line = line.rstrip()
                            print(f"🔧 {{line}}")  # Real-time Vivado output with prefix
                            stdout_capture.append(line)
                            # Also write to log immediately
                            with open(log_file_path, "a") as log:
                                log.write(line + "\\n")
                
                def read_stderr():
                    for line in iter(process.stderr.readline, ''):
                        if line:
                            line = line.rstrip()
                            print(f"⚠️  {{line}}")  # Real-time stderr with different prefix  
                            stderr_capture.append(line)
                            # Also write to log immediately
                            with open(log_file_path, "a") as log:
                                log.write("STDERR: " + line + "\\n")
                
                # Start threads for parallel reading
                stdout_thread = threading.Thread(target=read_stdout)
                stderr_thread = threading.Thread(target=read_stderr)
                
                stdout_thread.start()
                stderr_thread.start()
                
                # Wait for process completion
                return_code = process.wait()
                
                # Wait for all output to be processed
                stdout_thread.join()
                stderr_thread.join()
            
            print("=" * 60)
            print(f"🏁 Vivado execution completed with exit code: {{return_code}}")
            
            # Create result object compatible with existing code
            class StreamedResult:
                def __init__(self, returncode, stdout_lines, stderr_lines):
                    self.returncode = returncode
                    self.stdout = "\\n".join(stdout_lines)
                    self.stderr = "\\n".join(stderr_lines)
            
            result = StreamedResult(return_code, stdout_capture, stderr_capture)
            
        finally:
            # Always restore original working directory
            os.chdir(original_cwd)
            with open(log_file_path, "a") as log:
                log.write(f"  Restored working directory to: " + original_cwd + "\\n")
        
        # Log stdout and stderr
        with open(log_file_path, "a") as log:
            log.write(f"  Vivado exit code: " + str(result.returncode) + "\\n")
            if result.stdout:
                log.write(f"  STDOUT:\\n" + result.stdout + "\\n")
            if result.stderr:
                log.write(f"  STDERR:\\n" + result.stderr + "\\n")
        
        # Copy results back to original location
        original_cwd = Path(os.getcwd())
        
        # Copy back any new files created by Vivado
        result_patterns = ["*.bit", "*.bin", "*.mcs", "*.rpt", "*.log", "*.jou", "*.xpr"]
        copied_back = []
        
        for pattern in result_patterns:
            for result_file in workspace_path.glob(pattern):
                if result_file.is_file():
                    dest_path = original_cwd / result_file.name
                    shutil.copy2(result_file, dest_path)
                    copied_back.append(result_file.name)
        
        # Also copy back any run directories that were created
        for item in workspace_path.iterdir():
            if item.is_dir() and (item.name.endswith(".runs") or item.name.endswith(".sim") or item.name.endswith(".cache")):
                dest_dir = original_cwd / item.name
                if dest_dir.exists():
                    shutil.rmtree(dest_dir)
                shutil.copytree(item, dest_dir)
                copied_back.append(item.name + "/")
        
        with open(log_dir / "vivado_calls.log", "a") as log:
            if copied_back:
                log.write(f"  Copied back " + str(len(copied_back)) + " result files/directories: " + ', '.join(copied_back[:10]) + ('...' if len(copied_back) > 10 else '') + "\\n")
            else:
                log.write(f"  No result files to copy back\\n")
        
        # Leave workspace for debugging if Vivado failed
        if result.returncode != 0:
            with open(log_dir / "vivado_calls.log", "a") as log:
                log.write(f"  KEPT workspace for debugging: " + str(workspace_path) + "\\n")
        else:
            # Cleanup workspace only on success
            try:
                shutil.rmtree(workspace_path)
                with open(log_dir / "vivado_calls.log", "a") as log:
                    log.write(f"  Cleaned up workspace: " + str(workspace_path) + "\\n")
            except Exception as cleanup_error:
                with open(log_dir / "vivado_calls.log", "a") as log:
                    log.write(f"  Warning: Could not cleanup workspace: " + str(cleanup_error) + "\\n")
        
        sys.exit(result.returncode)
        
    except Exception as e:
        # Use absolute path for error logging
        try:
            error_log_path = Path(os.getcwd()) / log_dir / "vivado_calls.log"
            with open(error_log_path, "a") as log:
                log.write(f"  ERROR in Vivado wrapper: " + str(e) + "\\n")
        except Exception as log_error:
            # If logging fails, print both the original error and the logging error
            print(
                f"ERROR in Vivado wrapper: {e}; logging failed: {log_error}"
            )
        sys.exit(1)

if __name__ == "__main__":
    main()
'''
    
    with open(wrapper_path, 'w') as f:
        f.write(wrapper_content)
    
    os.chmod(wrapper_path, 0o755)
    logger.info(f"Created Vivado wrapper at: {wrapper_path}")
    return wrapper_path

def create_fusesoc_config(config: Dict[str, str], wrapper_path: Path, logger: logging.Logger) -> Path:
    """Create FuseSoC configuration file or use existing one"""
    
    # Check if FUSESOC_CONFIG environment variable is set (used by remote builds)
    existing_config = os.environ.get('FUSESOC_CONFIG')
    if existing_config and Path(existing_config).exists():
        logger.info(f"Using existing FuseSoC config: {existing_config}")
        return Path(existing_config)
    
    # Determine correct chisel cores path
    # Check if we're in gateware directory or repository root
    current_dir = Path.cwd()
    if current_dir.name == "gateware":
        # We're in gateware directory, use relative path
        cores_location = "chisel/cores"
    else:
        # We're in repository root, use full path
        cores_location = "gateware/chisel/cores"
    
    fusesoc_config = f"""[main]
build_root = {config['BUILD_ROOT']}
cache_root = {config['FUSESOC_CACHE']}
library_root = libraries

[library.retrobus]
location = {cores_location}
sync-uri = {cores_location}
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
    logger.info(f"Using cores location: {cores_location}")
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

def run_chisel_build(project_name: str, project_config: Dict, logger: logging.Logger) -> bool:
    """Run Chisel build to generate SystemVerilog"""
    logger.info("="*60)
    logger.info(f"Starting Chisel build for {project_name}")
    logger.info("="*60)
    
    try:
        # Check if we're in WSL
        if not Path("/mnt/c").exists():
            logger.error("This script must be run from WSL")
            return False
        
        # Determine correct chisel directory path
        current_dir = Path.cwd()
        if current_dir.name == "gateware":
            # We're in gateware directory, use relative path
            chisel_dir = Path("chisel")
        else:
            # We're in repository root, use full path
            chisel_dir = Path("gateware/chisel")
        
        if not chisel_dir.exists():
            logger.error(f"Chisel directory not found: {chisel_dir}")
            logger.error(f"Current working directory: {current_dir}")
            logger.error(f"Looked for chisel at: {chisel_dir.absolute()}")
            return False
        
        # Check for build.sbt
        build_sbt = chisel_dir / "build.sbt"
        if not build_sbt.exists():
            logger.error(f"build.sbt not found at: {build_sbt}")
            return False
        
        logger.info(f"Found build.sbt at: {build_sbt}")
        
        # Run SBT builds for all targets
        sbt_target = project_config["sbt_target"]
        additional_targets = project_config.get("additional_targets", [])
        all_targets = [sbt_target] + additional_targets
        
        for i, target in enumerate(all_targets):
            logger.info(f"Generating SystemVerilog with SBT target {i+1}/{len(all_targets)}: {target}")
            result = run_command_with_logging(
                ["sbt", target],
                chisel_dir,
                logger,
                f"SBT build {i+1}/{len(all_targets)}"
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
                generated_dir / "PinTesterTop.sv",
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
        list_cmd = [
            "fusesoc",
            f"--config={os.environ['FUSESOC_CONFIG']}" if 'FUSESOC_CONFIG' in os.environ else "",
            "core", 
            "list"
        ]
        # Remove empty strings from command
        list_cmd = [c for c in list_cmd if c]
        list_result = subprocess.run(list_cmd, env=env, capture_output=True, text=True)
        
        if list_result.returncode == 0:
            cores = [line for line in list_result.stdout.split('\n') if 'retrobus' in line]
            logger.info(f"Available retrobus cores: {cores}")
        
        # Build command
        cmd = [
            "fusesoc",
            f"--config={os.environ['FUSESOC_CONFIG']}" if 'FUSESOC_CONFIG' in os.environ else "",
            "--verbose" if config.get('LOG_LEVEL') == 'DEBUG' else "",
            "run",
            "--target=default",
            fusesoc_core
        ]
        
        # Remove empty strings from command
        cmd = [c for c in cmd if c]
        
        logger.info(f"Running FuseSoC command:")
        logger.info(f"  Command list: {cmd}")
        logger.info(f"  Joined command: {' '.join(cmd)}")
        logger.info(f"  Working directory: {os.getcwd()}")
        logger.info(f"  Environment variables:")
        for key in ['FUSESOC_CONFIG', 'EDALIZE_LAUNCHER']:
            if key in env:
                logger.info(f"    {key}={env[key]}")
        logger.debug(f"  Full environment: {dict(env)}")
        
        # Run FuseSoC with enhanced real-time output streaming
        print("\n🔨 Starting FuseSoC execution - real-time output:")
        print("=" * 60)
        
        process = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        # Stream output with emoji prefixes
        output_lines = []
        for line in process.stdout:
            line = line.rstrip()
            if line:
                output_lines.append(line)
                
                # Print with emoji prefixes for different message types
                if "ERROR" in line or "CRITICAL" in line:
                    print(f"❌ {line}")
                    logger.error(f"FuseSoC: {line}")
                elif "WARNING" in line:
                    print(f"⚠️  {line}")
                    logger.warning(f"FuseSoC: {line}")
                elif "vivado" in line.lower() or "synthesis" in line.lower() or "implementation" in line.lower():
                    print(f"🔧 {line}")
                    logger.info(f"FuseSoC: {line}")
                elif "INFO" in line:
                    print(f"ℹ️  {line}")
                    logger.info(f"FuseSoC: {line}")
                else:
                    print(f"📦 {line}")
                    logger.info(f"FuseSoC: {line}")
        
        print("=" * 60)
        print(f"🏁 FuseSoC execution completed")
        
        process.wait()
        
        if process.returncode != 0:
            logger.error(f"FuseSoC build failed with code: {process.returncode}")
            
            # Log specific error analysis
            error_lines = [line for line in output_lines if "ERROR" in line]
            if error_lines:
                logger.error("=== Specific Errors Found ===")
                for error_line in error_lines[:5]:  # Show first 5 errors
                    logger.error(f"  {error_line}")
                logger.error("=== End Specific Errors ===")
            
            # Check for dependency-related errors
            dependency_errors = [line for line in output_lines if "requires" in line and "not found" in line]
            if dependency_errors:
                logger.error("=== Dependency Resolution Errors ===")
                for dep_error in dependency_errors:
                    logger.error(f"  {dep_error}")
                logger.error("=== End Dependency Errors ===")
            
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
        print(f"Usage: {sys.argv[0]} <project_name> [--skip-chisel]")
        print("Options:")
        print("  --skip-chisel    Skip Chisel build step (use existing generated files)")
        print()
        print_available_projects()
        sys.exit(1)
    
    # Parse arguments
    project_name = sys.argv[1]
    skip_chisel = "--skip-chisel" in sys.argv[2:]
    
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
    
    # Log tool versions for debugging
    logger.info("=== Tool Versions ===")
    try:
        import subprocess
        # Get FuseSoC version
        fusesoc_version = subprocess.run(['fusesoc', '--version'], capture_output=True, text=True)
        if fusesoc_version.returncode == 0:
            logger.info(f"FuseSoC version: {fusesoc_version.stdout.strip()}")
        else:
            logger.info("FuseSoC version: Not available")
        
        # Get SBT version (will be logged during Chisel build)
        sbt_version = subprocess.run(['sbt', 'sbtVersion'], capture_output=True, text=True, cwd=Path("gateware/chisel"))
        if sbt_version.returncode == 0:
            # Extract version from SBT output
            for line in sbt_version.stdout.split('\n'):
                if 'sbt version' in line.lower() or line.strip().startswith('1.'):
                    logger.info(f"SBT version: {line.strip()}")
                    break
        else:
            logger.info("SBT version: Not available")
            
        # Get Java version
        java_version = subprocess.run(['java', '-version'], capture_output=True, text=True)
        if java_version.returncode == 0:
            # Java version goes to stderr
            first_line = java_version.stderr.split('\n')[0] if java_version.stderr else "Unknown"
            logger.info(f"Java version: {first_line}")
        else:
            logger.info("Java version: Not available")
            
    except Exception as e:
        logger.warning(f"Could not get tool versions: {e}")
    logger.info("=== End Tool Versions ===")
    
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
    
    # Step 3: Run Chisel build (optional)
    if skip_chisel:
        logger.info("\nStep 3/4: Skipping Chisel build (--skip-chisel specified)")
        logger.info("Using existing generated SystemVerilog files")
    else:
        logger.info("\nStep 3/4: Running Chisel build...")
        if not run_chisel_build(project_name, project_config, logger):
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