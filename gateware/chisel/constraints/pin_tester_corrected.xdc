# Pin Tester Constraint File for Alchitry Au FPGA
# Corrected with valid package pins for xc7a35tftg256-1
# Compatible with pin-tester Chisel implementation

# Standard Alchitry Au board pins
# These pins are standard across all Alchitry Au projects

# 100MHz Clock
set_property PACKAGE_PIN N14 [get_ports io_clk]
set_property IOSTANDARD LVCMOS33 [get_ports io_clk]
create_clock -period 10.000 -name clk -waveform {0.000 5.000} [get_ports io_clk]

# Reset button (active low)
set_property PACKAGE_PIN P6 [get_ports io_rst_n]
set_property IOSTANDARD LVCMOS33 [get_ports io_rst_n]

# User LEDs (8 LEDs)
set_property PACKAGE_PIN K13 [get_ports {io_led[0]}]
set_property PACKAGE_PIN K12 [get_ports {io_led[1]}]
set_property PACKAGE_PIN L14 [get_ports {io_led[2]}]
set_property PACKAGE_PIN L13 [get_ports {io_led[3]}]
set_property PACKAGE_PIN M16 [get_ports {io_led[4]}]
set_property PACKAGE_PIN M14 [get_ports {io_led[5]}]
set_property PACKAGE_PIN M12 [get_ports {io_led[6]}]
set_property PACKAGE_PIN N16 [get_ports {io_led[7]}]
set_property IOSTANDARD LVCMOS33 [get_ports {io_led[*]}]

# USB UART
set_property PACKAGE_PIN P15 [get_ports io_usb_rx]
set_property PACKAGE_PIN P16 [get_ports io_usb_tx]
set_property IOSTANDARD LVCMOS33 [get_ports io_usb_rx]
set_property IOSTANDARD LVCMOS33 [get_ports io_usb_tx]

# Saleae Logic Analyzer Output (8 pins)
set_property PACKAGE_PIN F4 [get_ports {io_saleae[0]}]
set_property PACKAGE_PIN F3 [get_ports {io_saleae[1]}]
set_property PACKAGE_PIN C4 [get_ports {io_saleae[2]}]
set_property PACKAGE_PIN D4 [get_ports {io_saleae[3]}]
set_property PACKAGE_PIN M15 [get_ports {io_saleae[4]}]
set_property PACKAGE_PIN P14 [get_ports {io_saleae[5]}]
set_property PACKAGE_PIN E1 [get_ports {io_saleae[6]}]
set_property PACKAGE_PIN F2 [get_ports {io_saleae[7]}]
set_property IOSTANDARD LVCMOS33 [get_ports {io_saleae[*]}]

# 48-bit FFC Data Bus (bidirectional)
# Using available IO pins on the Alchitry Au board
# Bank 0 (bits 0-7)
set_property PACKAGE_PIN B7 [get_ports {io_ffc_data[0]}]
set_property PACKAGE_PIN A7 [get_ports {io_ffc_data[1]}]
set_property PACKAGE_PIN B6 [get_ports {io_ffc_data[2]}]
set_property PACKAGE_PIN B5 [get_ports {io_ffc_data[3]}]
set_property PACKAGE_PIN A5 [get_ports {io_ffc_data[4]}]
set_property PACKAGE_PIN A4 [get_ports {io_ffc_data[5]}]
set_property PACKAGE_PIN B4 [get_ports {io_ffc_data[6]}]
set_property PACKAGE_PIN A3 [get_ports {io_ffc_data[7]}]

# Bank 1 (bits 8-15)
set_property PACKAGE_PIN C7 [get_ports {io_ffc_data[8]}]
set_property PACKAGE_PIN C6 [get_ports {io_ffc_data[9]}]
set_property PACKAGE_PIN D6 [get_ports {io_ffc_data[10]}]
set_property PACKAGE_PIN D5 [get_ports {io_ffc_data[11]}]
set_property PACKAGE_PIN G5 [get_ports {io_ffc_data[12]}]
set_property PACKAGE_PIN G4 [get_ports {io_ffc_data[13]}]
set_property PACKAGE_PIN G2 [get_ports {io_ffc_data[14]}]
set_property PACKAGE_PIN G1 [get_ports {io_ffc_data[15]}]

# Bank 2 (bits 16-23)
set_property PACKAGE_PIN L3 [get_ports {io_ffc_data[16]}]
set_property PACKAGE_PIN J1 [get_ports {io_ffc_data[17]}]
set_property PACKAGE_PIN P8 [get_ports {io_ffc_data[18]}]
set_property PACKAGE_PIN L2 [get_ports {io_ffc_data[19]}]
set_property PACKAGE_PIN N11 [get_ports {io_ffc_data[20]}]
set_property PACKAGE_PIN R8 [get_ports {io_ffc_data[21]}]
set_property PACKAGE_PIN P10 [get_ports {io_ffc_data[22]}]
set_property PACKAGE_PIN N12 [get_ports {io_ffc_data[23]}]

# Bank 3 (bits 24-31)
set_property PACKAGE_PIN C1 [get_ports {io_ffc_data[24]}]
set_property PACKAGE_PIN D1 [get_ports {io_ffc_data[25]}]
set_property PACKAGE_PIN J3 [get_ports {io_ffc_data[26]}]
set_property PACKAGE_PIN B1 [get_ports {io_ffc_data[27]}]
set_property PACKAGE_PIN R2 [get_ports {io_ffc_data[28]}]
set_property PACKAGE_PIN H3 [get_ports {io_ffc_data[29]}]
set_property PACKAGE_PIN N1 [get_ports {io_ffc_data[30]}]
set_property PACKAGE_PIN R1 [get_ports {io_ffc_data[31]}]

# Bank 4 (bits 32-39)
set_property PACKAGE_PIN M2 [get_ports {io_ffc_data[32]}]
set_property PACKAGE_PIN P1 [get_ports {io_ffc_data[33]}]
set_property PACKAGE_PIN N13 [get_ports {io_ffc_data[34]}]
set_property PACKAGE_PIN M1 [get_ports {io_ffc_data[35]}]
set_property PACKAGE_PIN E6 [get_ports {io_ffc_data[36]}]
set_property PACKAGE_PIN P13 [get_ports {io_ffc_data[37]}]
set_property PACKAGE_PIN K1 [get_ports {io_ffc_data[38]}]
set_property PACKAGE_PIN K5 [get_ports {io_ffc_data[39]}]

# Bank 5 (bits 40-47)
set_property PACKAGE_PIN R13 [get_ports {io_ffc_data[40]}]
set_property PACKAGE_PIN T12 [get_ports {io_ffc_data[41]}]
set_property PACKAGE_PIN R12 [get_ports {io_ffc_data[42]}]
set_property PACKAGE_PIN P11 [get_ports {io_ffc_data[43]}]
set_property PACKAGE_PIN T7 [get_ports {io_ffc_data[44]}]
set_property PACKAGE_PIN T5 [get_ports {io_ffc_data[45]}]
set_property PACKAGE_PIN R5 [get_ports {io_ffc_data[46]}]
set_property PACKAGE_PIN T13 [get_ports {io_ffc_data[47]}]

# Set IO standard for all FFC data pins (3.3V LVCMOS)
set_property IOSTANDARD LVCMOS33 [get_ports {io_ffc_data[*]}]

# Note: ffc_data pins are bidirectional - tristate handling done in top-level module