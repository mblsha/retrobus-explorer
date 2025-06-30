# Shared Library

This directory contains common modules shared across multiple FPGA projects to reduce code duplication.

## Structure

- `uart/` - UART communication modules
  - `my_uart_tx.luc` - Custom UART transmitter with configurable data width

## Usage

In your Alchitry project file (.alp), reference shared modules using relative paths:

```json
{
    "file": {
        "type": "DiskFile",
        "path": "../shared-lib/uart/my_uart_tx.luc"
    }
}
```

## Adding New Shared Modules

1. Verify the module is truly generic and used by multiple projects
2. Place it in the appropriate subdirectory
3. Update all projects to use the shared version
4. Remove duplicate copies from individual projects
5. Test all affected projects