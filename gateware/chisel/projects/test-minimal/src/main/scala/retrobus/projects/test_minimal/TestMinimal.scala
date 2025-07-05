package retrobus.projects.test_minimal

import chisel3._
import chisel3.util._
import retrobus.library.reset.ResetConditioner

/**
 * Test minimal project - simple counter with LED output
 * Migrated from Lucid version in test-minimal/source/alchitry_top.luc
 * 
 * This module implements a 26-bit counter that drives the LEDs
 * using the upper 8 bits for visible blinking at ~100MHz/2^18 = ~381Hz
 */
class AlchitryTop extends Module {
  val io = IO(new Bundle {
    val clk = Input(Clock())     // 100MHz clock (explicit for clarity)
    val rst_n = Input(Bool())    // reset button (active low)
    val led = Output(UInt(8.W))  // 8 user controllable LEDs
  })

  // Use the provided clock and reset
  withClock(io.clk) {
    // Reset conditioner
    val resetCond = Module(new ResetConditioner)
    resetCond.io.in := !io.rst_n  // invert reset signal
    
    // Use conditioned reset for the counter
    withReset(resetCond.io.out.asAsyncReset) {
      // 26-bit counter for LED blinking
      val counter = RegInit(0.U(26.W))
      
      // Increment counter
      counter := counter + 1.U
      
      // Use upper bits [25:18] for visible blinking
      io.led := counter(25, 18)
    }
  }
}

/**
 * Generator object for creating Verilog
 */
object TestMinimalVerilog extends App {
  // Generate Verilog
  emitVerilog(new AlchitryTop, Array("--target-dir", "generated"))
}