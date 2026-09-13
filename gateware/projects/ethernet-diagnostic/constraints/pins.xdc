# Arty A7-35T onboard DP83848J MII. Common DDR/SD pins live in build_ddr.py.
# Source: Digilent Arty-A7-35-Master.xdc; all Ethernet I/O uses 3.3 V.
set_property -dict { PACKAGE_PIN G18 IOSTANDARD LVCMOS33 } [get_ports {eth_ref_clk}];
set_property -dict { PACKAGE_PIN C16 IOSTANDARD LVCMOS33 } [get_ports {eth_rstn}];
set_property -dict { PACKAGE_PIN F15 IOSTANDARD LVCMOS33 } [get_ports {eth_rx_clk}];
set_property -dict { PACKAGE_PIN G16 IOSTANDARD LVCMOS33 } [get_ports {eth_rx_dv}];
set_property -dict { PACKAGE_PIN C17 IOSTANDARD LVCMOS33 } [get_ports {eth_rxerr}];
set_property -dict { PACKAGE_PIN H16 IOSTANDARD LVCMOS33 } [get_ports {eth_tx_clk}];
set_property -dict { PACKAGE_PIN H15 IOSTANDARD LVCMOS33 } [get_ports {eth_tx_en}];
set_property -dict { PACKAGE_PIN D18 IOSTANDARD LVCMOS33 } [get_ports {eth_rxd[0]}];
set_property -dict { PACKAGE_PIN E17 IOSTANDARD LVCMOS33 } [get_ports {eth_rxd[1]}];
set_property -dict { PACKAGE_PIN E18 IOSTANDARD LVCMOS33 } [get_ports {eth_rxd[2]}];
set_property -dict { PACKAGE_PIN G17 IOSTANDARD LVCMOS33 } [get_ports {eth_rxd[3]}];
set_property -dict { PACKAGE_PIN H14 IOSTANDARD LVCMOS33 } [get_ports {eth_txd[0]}];
set_property -dict { PACKAGE_PIN J14 IOSTANDARD LVCMOS33 } [get_ports {eth_txd[1]}];
set_property -dict { PACKAGE_PIN J13 IOSTANDARD LVCMOS33 } [get_ports {eth_txd[2]}];
set_property -dict { PACKAGE_PIN H17 IOSTANDARD LVCMOS33 } [get_ports {eth_txd[3]}];
create_clock -period 40.000 -name rx_clk [get_ports eth_rx_clk]
create_clock -period 40.000 -name tx_clk [get_ports eth_tx_clk]
