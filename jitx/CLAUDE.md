# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RetroBus Explorer is a hardware/software co-design project for interfacing with legacy 5V computer systems, particularly SHARP calculators and organizers. It combines:
- JITX/Stanza for PCB design of level-shifting adapters
- FPGA gateware (Spade/SystemVerilog) for bus capture and analysis
- Python tools for visualization and protocol decoding

## Build Commands

### JITX/Stanza PCB Design
```bash
# Generate PCB designs (outputs to designs/ directories)
stanza <design-file>.stanza
```

### Python Analysis Tools
```bash
# Run tests
cd ../py
pytest

# Run specific test
pytest z80bus/test_bus_parser.py
```

### FPGA Development

The canonical FPGA workspace is `../gateware`. Use Swim for Spade builds and
Cocotb with Verilator for behavioral testing:

```bash
cd ../gateware
uv sync --locked --all-packages
uv run python tools/project_inventory.py --check
uv run python tools/run_tb.py --project projects/pin-tester
```

## Architecture

### Directory Structure
- `jitx/` - PCB design files
  - `components/` - Hardware component definitions (level shifters, connectors, CPUs)
  - `stackups/` - PCB stackup configurations for flexible PCBs
  - `designs/` - Generated PCB design outputs
- `gateware/` - FPGA source code
  - `projects/` - Buildable Spade applications, diagnostics, and examples
  - `lib/shared-components/` - Reusable Spade modules and unit tests
  - `constraints/` - Shared board, interface, and target pin mappings
  - `rtl/vendor/` - Shared compatibility SystemVerilog
  - `tools/` - Test, inventory, constraint, build, and flash helpers
- `py/` - Python analysis tools
  - `z80bus/` - Z80 bus parsing and analysis
  - `shared/pyz80/` - Z80 CPU emulation library
  - `d3xx/` - FTDI USB3 driver interface

### Key Design Patterns
1. **Level Shifting**: Uses Texas Instruments SN74LVC8T245 and similar components for bidirectional level translation between 3.3V and 5V domains
2. **Bus Capture**: FPGA captures bus signals and streams via USB3 using FTDI FT601
3. **Protocol Analysis**: Python tools decode captured bus traffic for various protocols (Z80, display controllers, etc.)

## Stanza Syntax Reference

### Basic Syntax
- Comments: Use `;` for single-line comments
- Whitespace/indentation is significant
- Functions require space between name and arguments: `defn func-name (args)`

### Common Constructs
```stanza
; Package definition
defpackage my-package:
  import core
  import jitx
  import jitx/commands

; Function definition
defn my-function (arg: Int) -> String:
  match(arg):
    0: "Zero"
    else: "Non-zero"

; Variable declarations
val immutable-var = 42        ; Immutable
var mutable-var = "hello"     ; Mutable

; Component definition (JITX-specific)
pcb-component my-resistor:
  manufacturer = "Yageo"
  mpn = "RC0603FR-0710KL"
  val resistance = 10.0e3
```

### Key JITX-Specific Patterns
```stanza
; Pin definitions
port power : power
pin p[1] at Point(0.0, 0.0)

; Net connections
net VCC (supply.vdd, chip.power)

; Component instantiation
inst r : resistor(10.0e3)
```

### Type System
- Optional typing with `: Type` annotations
- Union types: `True|False`, `Int|Double`
- Generic types: `Array<T>`
- Pattern matching with `match()`

## Development Tips

1. **PCB Design Workflow**:
   - Modify component definitions in `components/`
   - Run stanza on design files to generate outputs
   - Check generated files in `designs/` directories

2. **FPGA Development**:
   - Project Spade sources and Cocotb tests live together under
     `gateware/projects/<name>/`
   - Reusable ACF inputs live under `gateware/constraints/`; checked-in project
     `constraints/pins.xdc` snapshots are regenerated and golden-tested
   - Test shared logic in `gateware/lib/shared-components/` and integration in
     the affected project

3. **Python Analysis**:
   - Bus captures are processed through `z80bus/BusParser`
   - Visualization uses Marimo notebooks
   - USB3 communication via `d3xx` wrapper

## Common Tasks

### Adding a New PCB Component
1. Create definition in `components/` directory
2. Import in main design file
3. Instantiate and connect in circuit

### Modifying FPGA Gateware
1. Add or update Cocotb characterization tests before changing behavior.
2. Edit the Spade source under `gateware/projects/<name>/src/`, or extract
   reusable logic to `gateware/lib/shared-components/src/`.
3. Update shared or project ACF inputs if pin assignments change.
4. Run the affected shared-component and project tests through
   `gateware/tools/run_tb.py` with Verilator.

### Analyzing Bus Captures
1. Use Python scripts in `py/` directory
2. Parse captures with `BusParser` class
3. Visualize with Marimo notebooks or export data
