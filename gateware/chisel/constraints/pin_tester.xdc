# Pin Tester Constraint File for Alchitry Au FPGA
# Converted from Alchitry .acf format to Xilinx .xdc format
# Compatible with pin-tester Chisel implementation

# Standard Alchitry Au board pins
# These pins are standard across all Alchitry Au projects

# 100MHz Clock
set_property PACKAGE_PIN P17 [get_ports io_clk]
set_property IOSTANDARD LVCMOS33 [get_ports io_clk]
create_clock -period 10.000 -name clk -waveform {0.000 5.000} [get_ports io_clk]

# Reset button (active low)
set_property PACKAGE_PIN P14 [get_ports io_rst_n]
set_property IOSTANDARD LVCMOS33 [get_ports io_rst_n]

# User LEDs (8 LEDs)
set_property PACKAGE_PIN J11 [get_ports {io_led[0]}]
set_property PACKAGE_PIN K11 [get_ports {io_led[1]}]
set_property PACKAGE_PIN L14 [get_ports {io_led[2]}]
set_property PACKAGE_PIN L15 [get_ports {io_led[3]}]
set_property PACKAGE_PIN M14 [get_ports {io_led[4]}]
set_property PACKAGE_PIN M15 [get_ports {io_led[5]}]
set_property PACKAGE_PIN M16 [get_ports {io_led[6]}]
set_property PACKAGE_PIN M17 [get_ports {io_led[7]}]
set_property IOSTANDARD LVCMOS33 [get_ports {io_led[*]}]

# USB UART
set_property PACKAGE_PIN P15 [get_ports io_usb_rx]
set_property PACKAGE_PIN P16 [get_ports io_usb_tx]
set_property IOSTANDARD LVCMOS33 [get_ports io_usb_rx]
set_property IOSTANDARD LVCMOS33 [get_ports io_usb_tx]

# Saleae Logic Analyzer Output (8 pins)
set_property PACKAGE_PIN D12 [get_ports {io_saleae[0]}]
set_property PACKAGE_PIN D11 [get_ports {io_saleae[1]}]
set_property PACKAGE_PIN B8 [get_ports {io_saleae[2]}]
set_property PACKAGE_PIN B9 [get_ports {io_saleae[3]}]
set_property PACKAGE_PIN B12 [get_ports {io_saleae[4]}]
set_property PACKAGE_PIN B11 [get_ports {io_saleae[5]}]
set_property PACKAGE_PIN B40 [get_ports {io_saleae[6]}]
set_property PACKAGE_PIN B39 [get_ports {io_saleae[7]}]
set_property IOSTANDARD LVCMOS33 [get_ports {io_saleae[*]}]

# 48-bit FFC Data Bus (bidirectional)
# Bank 0 (bits 0-7)
set_property PACKAGE_PIN A49 [get_ports {io_ffc_data[0]}]
set_property PACKAGE_PIN A48 [get_ports {io_ffc_data[1]}]
set_property PACKAGE_PIN A46 [get_ports {io_ffc_data[2]}]
set_property PACKAGE_PIN A45 [get_ports {io_ffc_data[3]}]
set_property PACKAGE_PIN A2 [get_ports {io_ffc_data[4]}]
set_property PACKAGE_PIN A3 [get_ports {io_ffc_data[5]}]
set_property PACKAGE_PIN A5 [get_ports {io_ffc_data[6]}]
set_property PACKAGE_PIN A6 [get_ports {io_ffc_data[7]}]

# Bank 1 (bits 8-15)
set_property PACKAGE_PIN C2 [get_ports {io_ffc_data[8]}]
set_property PACKAGE_PIN C3 [get_ports {io_ffc_data[9]}]
set_property PACKAGE_PIN C5 [get_ports {io_ffc_data[10]}]
set_property PACKAGE_PIN C6 [get_ports {io_ffc_data[11]}]
set_property PACKAGE_PIN C49 [get_ports {io_ffc_data[12]}]
set_property PACKAGE_PIN C48 [get_ports {io_ffc_data[13]}]
set_property PACKAGE_PIN C46 [get_ports {io_ffc_data[14]}]
set_property PACKAGE_PIN C45 [get_ports {io_ffc_data[15]}]

# Bank 2 (bits 16-23)
set_property PACKAGE_PIN A8 [get_ports {io_ffc_data[16]}]
set_property PACKAGE_PIN A9 [get_ports {io_ffc_data[17]}]
set_property PACKAGE_PIN A11 [get_ports {io_ffc_data[18]}]
set_property PACKAGE_PIN A12 [get_ports {io_ffc_data[19]}]
set_property PACKAGE_PIN A14 [get_ports {io_ffc_data[20]}]
set_property PACKAGE_PIN A15 [get_ports {io_ffc_data[21]}]
set_property PACKAGE_PIN A23 [get_ports {io_ffc_data[22]}]
set_property PACKAGE_PIN A24 [get_ports {io_ffc_data[23]}]

# Bank 3 (bits 24-31)
set_property PACKAGE_PIN C43 [get_ports {io_ffc_data[24]}]
set_property PACKAGE_PIN C42 [get_ports {io_ffc_data[25]}]
set_property PACKAGE_PIN C40 [get_ports {io_ffc_data[26]}]
set_property PACKAGE_PIN C39 [get_ports {io_ffc_data[27]}]
set_property PACKAGE_PIN C37 [get_ports {io_ffc_data[28]}]
set_property PACKAGE_PIN C36 [get_ports {io_ffc_data[29]}]
set_property PACKAGE_PIN C34 [get_ports {io_ffc_data[30]}]
set_property PACKAGE_PIN C33 [get_ports {io_ffc_data[31]}]

# Bank 4 (bits 32-39)
set_property PACKAGE_PIN A34 [get_ports {io_ffc_data[32]}]
set_property PACKAGE_PIN A33 [get_ports {io_ffc_data[33]}]
set_property PACKAGE_PIN B49 [get_ports {io_ffc_data[34]}]
set_property PACKAGE_PIN B48 [get_ports {io_ffc_data[35]}]
set_property PACKAGE_PIN B2 [get_ports {io_ffc_data[36]}]
set_property PACKAGE_PIN B3 [get_ports {io_ffc_data[37]}]
set_property PACKAGE_PIN B5 [get_ports {io_ffc_data[38]}]
set_property PACKAGE_PIN B6 [get_ports {io_ffc_data[39]}]

# Bank 5 (bits 40-47)
set_property PACKAGE_PIN C31 [get_ports {io_ffc_data[40]}]
set_property PACKAGE_PIN C30 [get_ports {io_ffc_data[41]}]
set_property PACKAGE_PIN C28 [get_ports {io_ffc_data[42]}]
set_property PACKAGE_PIN C27 [get_ports {io_ffc_data[43]}]
set_property PACKAGE_PIN D8 [get_ports {io_ffc_data[44]}]
set_property PACKAGE_PIN D9 [get_ports {io_ffc_data[45]}]
set_property PACKAGE_PIN D43 [get_ports {io_ffc_data[46]}]
set_property PACKAGE_PIN D42 [get_ports {io_ffc_data[47]}]

# Set IO standard for all FFC data pins (3.3V LVCMOS)
set_property IOSTANDARD LVCMOS33 [get_ports {io_ffc_data[*]}]

# Note: ffc_data pins are bidirectional - tristate handling done in top-level module