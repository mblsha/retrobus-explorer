package retrobus.library.uart

import chisel3._
import chisel3.util._

/**
 * UART Receiver module
 * Migrated from Alchitry Labs uart_rx component
 */
class UartRx(clkFreq: Int = 100_000_000, baud: Int = 1_000_000) extends Module {
  val io = IO(new Bundle {
    val rx = Input(Bool())          // Serial input
    val data = Output(UInt(8.W))    // Received data
    val newData = Output(Bool())    // Pulse when new data is ready
  })

  // Calculate timing parameters
  val clkPerBit = (clkFreq + baud) / baud - 1
  val ctrSize = log2Ceil(clkPerBit)

  // State machine
  object State extends ChiselEnum {
    val IDLE, WAIT_HALF, WAIT_FULL, WAIT_HIGH = Value
  }

  // Registers
  val state = RegInit(State.IDLE)
  val ctr = RegInit(0.U(ctrSize.W))
  val bitCtr = RegInit(0.U(3.W))
  val savedData = RegInit(0.U(8.W))
  val newDataBuffer = RegInit(false.B)
  val rxd = RegInit(VecInit(Seq.fill(3)(true.B))) // Synchronizer shift register

  // Synchronize input
  rxd(0) := io.rx
  for (i <- 1 until 3) {
    rxd(i) := rxd(i-1)
  }

  // Default outputs
  io.data := savedData
  io.newData := newDataBuffer
  newDataBuffer := false.B

  switch(state) {
    is(State.IDLE) {
      bitCtr := 0.U
      ctr := 0.U
      when(!rxd(2)) { // Start bit detected
        state := State.WAIT_HALF
      }
    }

    is(State.WAIT_HALF) {
      ctr := ctr + 1.U
      when(ctr === (clkPerBit >> 1).U) {
        ctr := 0.U
        state := State.WAIT_FULL
      }
    }

    is(State.WAIT_FULL) {
      ctr := ctr + 1.U
      when(ctr === clkPerBit.U) {
        ctr := 0.U
        savedData := Cat(rxd(2), savedData(7, 1)) // Shift in LSB first
        bitCtr := bitCtr + 1.U
        when(bitCtr === 7.U) {
          state := State.WAIT_HIGH
        }
      }
    }

    is(State.WAIT_HIGH) {
      ctr := ctr + 1.U
      when(ctr === clkPerBit.U) {
        newDataBuffer := true.B
        state := State.IDLE
      }
    }
  }
}