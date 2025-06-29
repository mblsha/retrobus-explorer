# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

RetroBus Explorer is an FPGA-based platform for capturing and analyzing signals from legacy 5V system buses, particularly Sharp pocket computers. The project combines FPGA gateware (in Lucid HDL), Python analysis tools, and hardware PCB designs.

## Development Environment

### FPGA Development
- **Primary Tool**: Alchitry Labs V2 (requires Java 22)
- **HDL Language**: Lucid (.luc files) - compiles to Verilog
- **Target FPGA**: Xilinx Artix-7 (Alchitry Au board)
- **Local Testing**: Container-based environment matching GitHub CI

### Key Commands

**Check FPGA project syntax (CI command):**
```bash
alchitry check /absolute/path/to/project.alp
```

**Run tests locally on macOS using container:**
```bash
# Build the container (one-time setup)
./.github/container/build.sh

# Test all projects
./.github/container/test.sh

# Test specific project(s)
./.github/container/test.sh sharp-pc-g850-bus pin-tester
```

**Build Python Z80 emulator extension:**
```bash
cd py/shared/pyz80
python setup.py build
python setup.py install
```

**Run Python tests:**
```bash
PYTHONPATH=/path/to/py python3 -m unittest z80bus.test_bus_parser
```

**Start analysis server:**
```bash
python3 -m uvicorn z80bus.server:app
```

## Architecture

### FPGA Projects Structure
Each FPGA project follows this pattern:
```
project-name/
├── project-name.alp      # Alchitry project file (JSON)
├── source/               # Lucid HDL modules
│   ├── alchitry_top.luc # Top-level module (entry point)
│   └── *.luc            # Additional modules
├── constraint/           # Pin mapping files (.acf)
├── cores/               # Xilinx IP cores (.xci files)
└── build/               # Generated outputs
```

### Key FPGA Projects
- **pin-tester**: Hardware verification for 48-pin level shifter interface
- **sharp-pc-g850-bus**: Z80 bus analyzer for PC-G850
- **sharp-pc-g850-streaming-rom**: ROM emulator with USB3 streaming

### Python Tools Architecture
- **d3xx/**: FTDI D3XX USB3 driver wrapper (platform-specific)
- **z80bus/**: Core analysis modules
  - `bus_parser.py`: Decodes Z80 bus traffic
  - `server.py`: FastAPI server for real-time analysis
  - `sed1560.py`: LCD controller interpreter
  - `key_matrix.py`: Keyboard matrix decoder
- **Marimo notebooks**: Interactive analysis tools (.py files with marimo decorators)

### Hardware Interface
- 48-pin FFC connector through level shifters (6 banks of 8 pins)
- FT600 FTDI chip for USB3 data streaming (up to 200MB/s)
- Multiple constraint files map logical signals to physical pins

## Critical Implementation Details

1. **Pin Mappings**: The level-shifter.acf file maps 48 FPGA pins through banks. When modifying pin assignments, ensure bank alignment is maintained.

2. **Clock Domains**: Projects use Xilinx clk_wiz IP core for clock management. The USB domain runs at 100MHz, while captured buses may have different clock rates.

3. **Data Flow**: 
   - FPGA captures bus signals → FIFOs buffer data → FT600 streams to PC
   - Python tools parse the stream and provide real-time visualization

4. **Alchitry Components**: Projects reuse standard components like reset_conditioner, uart_rx/tx, and various FIFO implementations from Alchitry's library.

## Python Dependencies

The Python tools require (install manually as no requirements.txt exists):
- marimo
- fastapi, uvicorn, websockets
- PIL/Pillow
- pandas, altair
- lark
- pybind11 (for building pyz80)

## CI/CD

GitHub Actions runs syntax checks on all FPGA projects when gateware files change. The workflow downloads the latest Alchitry Labs V2 and validates each project.

### Local Testing Environment

The project includes a containerized testing environment that exactly matches the GitHub Actions CI:

1. **Container Setup**: Uses Ubuntu 22.04 with Java 22 and Alchitry Labs V2
2. **Shared Test Logic**: The same `test-core.sh` script is used by both local containers and GitHub Actions
3. **Container Runtime**: Supports both Apple Container (`container`) and Docker
4. **Architecture**: Runs natively on ARM64 (Apple Silicon)

To run tests locally:
```bash
# One-time setup
./.github/container/build.sh  # For Apple Container
# OR
./.github/container/docker-build.sh  # For Docker

# Run tests (automatically detects container runtime)
./.github/container/test.sh
```

## Lucid HDL Language Reference

**Full Reference**: https://alchitry.com/tutorials/lucid-reference/

### Essential Lucid Syntax

#### Module Structure
```lucid
module module_name #(
    PARAM = default_value : constraint
)(
    input signal_name,
    output reg_name[WIDTH]
) {
    // Module body
}
```

#### Signal Types
- `sig` - Combinational signal (must have single driver)
- `dff` - D flip-flop for sequential logic
- `const` - Named constants
- `var` - Variables (for loops/functions only)

#### Key Differences from Verilog
1. **Must drive ALL bits** of any signal in always blocks
2. **No reg/wire distinction** - use `sig` or `dff`
3. **Built-in DFF primitive** - no `always @(posedge clk)` needed
4. **Array syntax** - consistent use of `[SIZE]` brackets

#### Common Patterns
```lucid
// Sequential logic with DFF
dff counter[8](#INIT(0), .clk(clk), .rst(rst))

always {
    counter.d = counter.q + 1  // .d is input, .q is output
}

// Always block - drives signals completely
always {
    result = 0  // Default assignment first!
    if (condition) {
        result = 8hFF  // Then conditional assignments
    }
}

// Case statement for state machines
case (state.q) {
    States.IDLE: state.d = States.ACTIVE
    States.ACTIVE: state.d = States.DONE
    default: state.d = States.IDLE
}
```

#### Built-in Functions
- `$clog2(n)` - Calculate bit width needed for n values
- `$signed(value)` - Mark as signed
- `$reverse(array)` - Reverse array indices
- `$width(signal)` - Get signal width

#### Common Gotchas
```lucid
// WRONG - partial assignment
always {
    if (cond) result[3:0] = 4b1111  // Error!
}

// CORRECT - drive all bits
always {
    result = 0
    if (cond) result[3:0] = 4b1111  // OK now
}
```