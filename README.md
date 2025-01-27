# RetroBus Explorer

RetroBus Explorer is an FPGA-based platform designed to capture, analyze, and visualize signals from legacy 5V system buses. It uses a specialized level-shifting interface board for bus compatibility, streams the captured data through an F600 FTDI chip, and presents live waveforms, decoded protocols, and analytics via a JavaScript (WebUSB) interface in the browser.

# Hardware

Project is built on top of [Alchitry Au FPGA board](https://www.sparkfun.com/alchitry-au-fpga-development-board-xilinx-artix-7.html) and [Ft Element board](https://www.sparkfun.com/alchitry-ft-element-board.html). To interface with the 5V bus, a Level Shifter Element board is used.

Hardware adapters connect the Level Shifter Element board to the target system. Up to 48 signals can be captured simultaneously.

Up to two adapters can be connected at the same time, allowing to capture communication on the system bus and the external bus card.

# Hardware Adapters

* Pin Tester to test correctness and signal integrity
* SHARP PC-G850
* SHARP PC-E500

# License

* PCB Design Files
All PCB design files are distributed under the
`CERN Open Hardware Licence Version 2 – Permissive`.

* Software (HDL, JS, etc.)
All other repository contents—including FPGA gateware (HDL), JavaScript frontend, and server code—are released under the `Apache License 2.0`.

You are free to use, modify, and distribute both portions of this project under their respective terms.


