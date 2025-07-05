package retrobus.library.uart

import chisel3._
import chisel3.util._

/**
 * Custom UART transmitter with configurable data width
 * Supports any data width, not just 8 bits
 * 
 * @param clkFreq Clock frequency in Hz
 * @param baud Baud rate in Hz
 * @param dataWidth Width of data to transmit
 */
class MyUartTx(clkFreq: Int = 100_000_000, baud: Int = 1_000_000, dataWidth: Int = 8) extends Module {
  val io = IO(new Bundle {
    val tx = Output(Bool())
    val block = Input(Bool())
    val busy = Output(Bool())
    val data = Input(UInt(dataWidth.W))
    val newData = Input(Bool())
  })

  // Calculate clocks per bit
  val clksPerBit = (clkFreq + baud) / baud - 1
  val ctrSize = log2Ceil(clksPerBit + 1)
  
  // State machine states
  object State extends ChiselEnum {
    val IDLE, START_BIT, DATA, STOP_BIT = Value
  }
  
  // State registers
  val state = RegInit(State.IDLE)
  val ctr = RegInit(0.U(ctrSize.W))
  val bitCtr = RegInit(0.U(log2Ceil(dataWidth + 1).W))
  val savedData = RegInit(0.U(dataWidth.W))
  val txReg = RegInit(true.B)
  val blockFlag = RegInit(false.B)
  
  // Default outputs
  io.tx := txReg
  io.busy := true.B
  
  // Update block flag
  blockFlag := io.block
  
  switch(state) {
    is(State.IDLE) {
      txReg := true.B // Line idle high
      when(!blockFlag) {
        io.busy := false.B
        bitCtr := 0.U
        ctr := 0.U
        when(io.newData) {
          savedData := io.data
          state := State.START_BIT
        }
      }
    }
    
    is(State.START_BIT) {
      ctr := ctr + 1.U
      txReg := false.B // Start bit is low
      when(ctr === (clksPerBit - 1).U) {
        ctr := 0.U
        state := State.DATA
      }
    }
    
    is(State.DATA) {
      ctr := ctr + 1.U
      txReg := savedData(bitCtr)
      when(ctr === (clksPerBit - 1).U) {
        ctr := 0.U
        bitCtr := bitCtr + 1.U
        when(bitCtr === (dataWidth - 1).U) {
          state := State.STOP_BIT
        }
      }
    }
    
    is(State.STOP_BIT) {
      ctr := ctr + 1.U
      txReg := true.B // Stop bit is high
      when(ctr === (clksPerBit - 1).U) {
        state := State.IDLE
      }
    }
  }
}