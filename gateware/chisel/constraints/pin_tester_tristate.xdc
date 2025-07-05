# Additional constraints for handling bidirectional ffc_data pins
# This file provides tristate buffer implementation for the 48-bit ffc_data bus

# Note: For proper bidirectional pin handling in Xilinx FPGAs, the following approach is used:
# 1. The Chisel design exposes separate ffc_data_in, ffc_data_out, and ffc_data_oe signals
# 2. External tristate buffers (IOBUF primitives) are instantiated to connect these to the physical pins
# 3. The pin constraint file (pin_tester.xdc) maps the actual pin locations

# Example Verilog tristate buffer instantiation that would be added by synthesis tools:
# (This is handled automatically by Vivado when proper IOBUF constraints are used)

# For each ffc_data bit, tristate buffers should be instantiated as follows:
# 
# IOBUF #(
#   .DRIVE(12),       // Specify drive strength
#   .IOSTANDARD("LVCMOS33"), // I/O standard
#   .SLEW("SLOW")     // Specify slew rate
# ) IOBUF_ffc_data[i] (
#   .O(ffc_data_in[i]),    // Buffer output (to fabric)
#   .IO(ffc_data[i]),      // Buffer inout port (to/from pin)
#   .I(ffc_data_out[i]),   // Buffer input (from fabric)
#   .T(!ffc_data_oe)       // 3-state enable input (active low)
# );

# Set additional properties for ffc_data pins
set_property DRIVE 12 [get_ports {io_ffc_data[*]}]
set_property SLEW SLOW [get_ports {io_ffc_data[*]}]

# Timing constraints for ffc_data bus
# These pins are used for relatively slow I/O testing, so relaxed timing is acceptable
set_false_path -from [get_ports {io_ffc_data[*]}] -to [all_clocks]
set_false_path -from [all_clocks] -to [get_ports {io_ffc_data[*]}]

# Group ffc_data pins for easier analysis
create_debug_port u_ila_0 probe0
set_property PROBE_TYPE DATA_AND_TRIGGER [get_debug_ports u_ila_0/probe0]
set_property port_width 48 [get_debug_ports u_ila_0/probe0]