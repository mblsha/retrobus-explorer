package retrobus.projects.pin_tester

import chisel3._
import chisel3.experimental._

/**
 * Top-level wrapper for pin-tester with proper bidirectional pin handling
 * This module instantiates the PinTesterTop and handles bidirectional pins
 * using Verilog to properly instantiate Xilinx IOBUFs
 */
class PinTesterBidirectional extends RawModule {
  val io = IO(new Bundle {
    val clk = Input(Clock())          // 100MHz clock
    val rst_n = Input(Bool())         // reset button (active low)
    val led = Output(UInt(8.W))       // 8 user controllable LEDs
    val usb_rx = Input(Bool())        // USB->Serial input
    val usb_tx = Output(Bool())       // USB->Serial output
    val ffc_data = Analog(48.W)       // Bidirectional 48-bit FFC data bus
    val saleae = Output(UInt(8.W))    // 8-bit Saleae logic analyzer output
  })

  // Create intermediate signals for the bidirectional interface
  val ffc_data_in = Wire(UInt(48.W))
  val ffc_data_out = Wire(UInt(48.W))
  val ffc_data_oe = Wire(Bool())

  // Instantiate the main pin-tester logic (which has PinTesterTop internally)
  withClockAndReset(io.clk, ~io.rst_n) {
    val pinTester = Module(new PinTesterTop)
    pinTester.io.clk := io.clk
    pinTester.io.rst_n := io.rst_n
    
    // Connect all signals
    io.led := pinTester.io.led
    pinTester.io.usb_rx := io.usb_rx
    io.usb_tx := pinTester.io.usb_tx
    pinTester.io.ffc_data_in := ffc_data_in
    ffc_data_out := pinTester.io.ffc_data_out
    ffc_data_oe := pinTester.io.ffc_data_oe
    io.saleae := pinTester.io.saleae
  }

  // BlackBox to handle bidirectional IOBUFs (doesn't need clock context)
  val iobufGen = Module(new IOBUFGenerator)
  iobufGen.io.I := ffc_data_out
  iobufGen.io.T := ~ffc_data_oe  // T=0 means output, T=1 means input
  attach(iobufGen.io.IO, io.ffc_data)
  ffc_data_in := iobufGen.io.O
}

/**
 * BlackBox wrapper for generating Xilinx IOBUF primitives
 * This will be replaced by actual IOBUF instantiations in the generated Verilog
 */
class IOBUFGenerator extends BlackBox {
  val io = IO(new Bundle {
    val I = Input(UInt(48.W))   // Input data (to pad)
    val O = Output(UInt(48.W))  // Output data (from pad)
    val T = Input(Bool())       // Tristate control (1=input, 0=output)
    val IO = Analog(48.W)       // Bidirectional pad connection
  })
  
  override def desiredName = "IOBUFGenerator"
}

/**
 * Generator object for creating Verilog with bidirectional pins
 */
object PinTesterBidirectionalVerilog extends App {
  // Generate Verilog with proper bidirectional handling
  emitVerilog(new PinTesterBidirectional, Array("--target-dir", "generated"))
  
  // Also create the IOBUFGenerator Verilog file
  val iobufVerilog = """module IOBUFGenerator (
  input [47:0] I,
  output [47:0] O,
  input T,
  inout [47:0] IO
);
  
  genvar i;
  generate
    for (i = 0; i < 48; i = i + 1) begin : gen_iobuf
      IOBUF iobuf_inst (
        .I(I[i]),
        .O(O[i]),
        .T(T),
        .IO(IO[i])
      );
    end
  endgenerate
  
endmodule
"""
  
  val fw = new java.io.FileWriter("generated/IOBUFGenerator.v")
  fw.write(iobufVerilog)
  fw.close()
}