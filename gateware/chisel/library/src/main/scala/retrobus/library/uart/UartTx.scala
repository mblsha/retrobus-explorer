package retrobus.library.uart

import chisel3._
import chisel3.util._

/**
 * UART Transmitter module
 * Migrated from Alchitry Labs uart_tx component
 */
class UartTx(clkFreq: Int = 100_000_000, baud: Int = 1_000_000) extends Module {
  val io = IO(new Bundle {
    val tx = Output(Bool())         // Serial output
    val block = Input(Bool())       // Block transmission
    val busy = Output(Bool())       // Transmission in progress
    val data = Input(UInt(8.W))     // Data to transmit
    val newData = Input(Bool())     // Start transmission
  })

  // Calculate timing parameters
  val clkPerBit = (clkFreq + baud) / baud - 1
  val ctrSize = log2Ceil(clkPerBit)

  // State machine
  object State extends ChiselEnum {
    val IDLE, START_BIT, DATA, STOP_BIT = Value
  }

  // Registers
  val state = RegInit(State.IDLE)
  val ctr = RegInit(0.U(ctrSize.W))
  val bitCtr = RegInit(0.U(3.W))
  val savedData = RegInit(0.U(8.W))
  val txReg = RegInit(true.B)  // UART idle high
  val blockFlag = RegInit(false.B)

  // Outputs
  io.tx := txReg
  io.busy := state =/= State.IDLE

  switch(state) {
    is(State.IDLE) {
      txReg := true.B
      when(io.newData && !io.block) {
        savedData := io.data
        state := State.START_BIT
        ctr := 0.U
        bitCtr := 0.U
        blockFlag := false.B
      }.elsewhen(io.block) {
        blockFlag := true.B
      }
    }

    is(State.START_BIT) {
      txReg := false.B // Start bit is low
      ctr := ctr + 1.U
      when(ctr === clkPerBit.U) {
        ctr := 0.U
        state := State.DATA
      }
    }

    is(State.DATA) {
      txReg := savedData(bitCtr)
      ctr := ctr + 1.U
      when(ctr === clkPerBit.U) {
        ctr := 0.U
        bitCtr := bitCtr + 1.U
        when(bitCtr === 7.U) {
          state := State.STOP_BIT
        }
      }
    }

    is(State.STOP_BIT) {
      txReg := true.B // Stop bit is high
      ctr := ctr + 1.U
      when(ctr === clkPerBit.U) {
        when(blockFlag) {
          // Stay in STOP_BIT until unblocked
          when(!io.block) {
            state := State.IDLE
            blockFlag := false.B
          }
        }.otherwise {
          state := State.IDLE
        }
      }
    }
  }
}