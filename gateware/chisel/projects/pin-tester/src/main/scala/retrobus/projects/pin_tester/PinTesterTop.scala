package retrobus.projects.pin_tester

import chisel3._

/**
 * Top-level wrapper for pin-tester that exposes bidirectional ffc_data interface
 * Bidirectional pin handling will be done at the platform/synthesis level
 * using constraints and tristate buffers in the generated Verilog
 */
class PinTesterTop extends Module {
  val io = IO(new Bundle {
    val clk = Input(Clock())          // 100MHz clock
    val rst_n = Input(Bool())         // reset button (active low)
    val led = Output(UInt(8.W))       // 8 user controllable LEDs
    val usb_rx = Input(Bool())        // USB->Serial input
    val usb_tx = Output(Bool())       // USB->Serial output
    // Bidirectional ffc_data broken into separate signals for platform handling
    val ffc_data_in = Input(UInt(48.W))    // Data read from pins
    val ffc_data_out = Output(UInt(48.W))  // Data to drive to pins
    val ffc_data_oe = Output(Bool())       // Output enable
    val saleae = Output(UInt(8.W))    // 8-bit Saleae logic analyzer output
  })

  // Instantiate the main pin-tester logic
  val pinTester = Module(new AlchitryTop)
  
  // Connect all signals directly - bidirectional handling done externally
  pinTester.io.clk := io.clk
  pinTester.io.rst_n := io.rst_n
  io.led := pinTester.io.led
  pinTester.io.usb_rx := io.usb_rx
  io.usb_tx := pinTester.io.usb_tx
  pinTester.io.ffc_data_in := io.ffc_data_in
  io.ffc_data_out := pinTester.io.ffc_data_out
  io.ffc_data_oe := pinTester.io.ffc_data_oe
  io.saleae := pinTester.io.saleae
}

/**
 * Generator object for creating Verilog
 */
object PinTesterTopVerilog extends App {
  // Generate Verilog - bidirectional handling will be added by synthesis tools
  emitVerilog(new PinTesterTop, Array("--target-dir", "generated"))
}