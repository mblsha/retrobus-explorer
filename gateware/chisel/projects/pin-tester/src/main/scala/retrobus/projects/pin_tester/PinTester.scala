package retrobus.projects.pin_tester

import chisel3._
import chisel3.util._
import retrobus.library.reset.ResetConditioner
import retrobus.library.uart.{UartRx, UartTx}

/**
 * Pin Tester project - I/O testing and bus analysis
 * Migrated from Lucid version in pin-tester/source/alchitry_top.luc
 * 
 * This module implements a pin tester with two modes:
 * - RECEIVE mode: Displays input data from ffc_data on LEDs/saleae
 * - SEND mode: Generates counter data and outputs on ffc_data/LEDs/saleae
 * 
 * UART commands:
 * - '0'-'5': Select bank (0-5) for 8-bit sections of 48-bit ffc_data
 * - 's'/'S': Switch to SEND mode
 * - 'r'/'R': Switch to RECEIVE mode
 */
class AlchitryTop extends Module {
  val io = IO(new Bundle {
    val clk = Input(Clock())          // 100MHz clock (explicit for clarity)
    val rst_n = Input(Bool())         // reset button (active low)
    val led = Output(UInt(8.W))       // 8 user controllable LEDs
    val usb_rx = Input(Bool())        // USB->Serial input
    val usb_tx = Output(Bool())       // USB->Serial output
    // Note: ffc_data bidirectional handling is platform-specific
    // In actual implementation, this would need tristate buffers at top level
    val saleae = Output(UInt(8.W))    // 8-bit Saleae logic analyzer output
  })

  // Use the provided clock
  withClock(io.clk) {
    // Reset conditioner
    val resetCond = Module(new ResetConditioner)
    resetCond.io.in := !io.rst_n  // invert reset signal
    
    // Use conditioned reset for all logic
    withReset(resetCond.io.out.asAsyncReset) {
      
      // Constants
      val OUT_BANK_MULTIPLIER = 2
      
      // State machine
      object States extends ChiselEnum {
        val RECEIVE, SEND = Value
      }

      // UART modules with 1Mbaud rate
      val uart_tx = Module(new UartTx(clkFreq = 100_000_000, baud = 1_000_000))
      val uart_rx = Module(new UartRx(clkFreq = 100_000_000, baud = 1_000_000))

      // Connect UART to external pins
      io.usb_tx := uart_tx.io.tx
      uart_rx.io.rx := io.usb_rx

      // State registers
      val state = RegInit(States.RECEIVE)
      val bank = RegInit(0.U(8.W))
      val counter = RegInit(0.U(128.W))

      // Default UART connections
      uart_tx.io.block := false.B
      uart_tx.io.data := 0.U
      uart_tx.io.newData := false.B

      // Default outputs
      io.led := 0.U
      io.saleae := 0.U

      // Bidirectional ffc_data handling would be done at platform level
      // For now we'll simulate with internal signals for testing
      val ffc_data_in = Wire(UInt(48.W))
      ffc_data_in := 0.U // Would be connected to actual pins in platform

      // State machine logic
      switch(state) {
        is(States.RECEIVE) {
          // Display input data on outputs
          val bankOffset = bank * 8.U
          val selectedData = (ffc_data_in >> bankOffset)(7, 0)
          io.led := selectedData
          io.saleae := selectedData

          // Handle UART commands
          when(uart_rx.io.newData) {
            val rxData = uart_rx.io.data

            // Bank selection commands ('0' to '5')
            when(rxData >= 48.U && rxData <= 53.U) { // ASCII '0' = 48, '5' = 53
              bank := rxData - 48.U
              
              // Echo command back
              when(!uart_tx.io.busy) {
                uart_tx.io.newData := true.B
                uart_tx.io.data := rxData
              }
            }
            // Switch to SEND mode ('s' or 'S')
            .elsewhen(rxData === 115.U || rxData === 83.U) { // ASCII 's' = 115, 'S' = 83
              when(!uart_tx.io.busy) {
                uart_tx.io.newData := true.B
                uart_tx.io.data := rxData
              }
              bank := 0.U
              state := States.SEND
            }
          }
        }

        is(States.SEND) {
          // Increment counter
          counter := counter + 1.U

          // Output counter data
          val bankOffset = bank * OUT_BANK_MULTIPLIER.U
          val selectedCounter = (counter >> bankOffset)(7, 0)
          io.led := selectedCounter
          io.saleae := selectedCounter

          // In real implementation, would drive ffc_data with counter
          // ffc_data_out := selectedCounter
          // ffc_data_oe := true.B

          // Handle UART commands
          when(uart_rx.io.newData) {
            val rxData = uart_rx.io.data

            // Bank selection commands ('0' to '5')
            when(rxData >= 48.U && rxData <= 53.U) { // ASCII '0' = 48, '5' = 53
              bank := rxData - 48.U
              
              // Echo command back
              when(!uart_tx.io.busy) {
                uart_tx.io.newData := true.B
                uart_tx.io.data := rxData
              }
            }
            // Switch to RECEIVE mode ('r' or 'R')
            .elsewhen(rxData === 114.U || rxData === 82.U) { // ASCII 'r' = 114, 'R' = 82
              when(!uart_tx.io.busy) {
                uart_tx.io.newData := true.B
                uart_tx.io.data := rxData
              }
              bank := 0.U
              state := States.RECEIVE
            }
          }
        }
      }

      // Note: Actual ffc_data bidirectional handling needs platform-specific implementation
      // This would typically be handled at the top-level with tristate buffers
    }
  }
}

/**
 * Generator object for creating Verilog
 */
object PinTesterVerilog extends App {
  // Generate Verilog
  emitVerilog(new AlchitryTop, Array("--target-dir", "generated"))
}