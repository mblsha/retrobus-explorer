package retrobus.library.ft

import chisel3._
import chisel3.util._
import retrobus.library.common._

/**
 * FT2232H synchronous FIFO interface
 * This version uses the testable interface for now
 * A real implementation would need IOBUF primitives for bidirectional signals
 * 
 * @param rxSize Size of RX buffer (default 64)
 * @param txSize Size of TX buffer (default 8192)
 */
class FT2232H(rxSize: Int = 64, txSize: Int = 8192) extends Module {
  val io = IO(new Bundle {
    // FT2232H interface (simplified)
    val ftClk = Input(Clock())
    val ftRxf = Input(Bool())
    val ftTxe = Input(Bool())
    val ftDataIn = Input(UInt(16.W))
    val ftDataOut = Output(UInt(16.W))
    val ftDataOutEn = Output(Bool())
    val ftBeOut = Output(UInt(2.W))
    val ftBeOutEn = Output(Bool())
    val ftRd = Output(Bool())
    val ftWr = Output(Bool())
    val ftOe = Output(Bool())
    
    // User interface
    val rxData = Output(UInt(16.W))
    val rxValid = Output(Bool())
    val txData = Input(UInt(16.W))
    val txWrite = Input(Bool())
    val txFull = Output(Bool())
  })

  // Default outputs
  io.ftRd := true.B
  io.ftWr := true.B
  io.ftOe := true.B
  io.ftDataOut := 0.U
  io.ftDataOutEn := false.B
  io.ftBeOut := 0.U
  io.ftBeOutEn := false.B
  
  // State machine
  object State extends ChiselEnum {
    val GET_FIFO, STREAM = Value
  }
  val state = RegInit(State.GET_FIFO)
  
  // TX FIFO
  val txFifo = Module(new Fifo(width = 16, depth = txSize))
  txFifo.io.din := io.txData
  txFifo.io.wr_en := io.txWrite
  txFifo.io.rd_en := false.B
  io.txFull := txFifo.io.full
  
  // Pipeline stages for FT signals
  val ftRxfSync = ShiftRegister(io.ftRxf, 2)
  val ftTxeSync = ShiftRegister(io.ftTxe, 2)
  
  // Data output register for driving ftData
  val dataOut = RegInit(0.U(16.W))
  val dataOutEn = RegInit(false.B)
  
  // Output data and byte enables
  io.ftDataOut := dataOut
  io.ftDataOutEn := dataOutEn
  io.ftBeOut := "b11".U  // Both bytes enabled
  io.ftBeOutEn := dataOutEn
  
  // RX data capture
  val rxDataReg = RegInit(0.U(16.W))
  val rxValidReg = RegInit(false.B)
  io.rxData := rxDataReg
  io.rxValid := rxValidReg
  
  // Default
  rxValidReg := false.B
  
  switch(state) {
    is(State.GET_FIFO) {
      // Read from FT2232H
      when(!ftRxfSync) {
        io.ftOe := false.B  // Enable output from FT
        io.ftRd := false.B  // Assert read
        state := State.GET_FIFO
        
        // Capture data on next cycle
        rxValidReg := true.B
        rxDataReg := io.ftDataIn
      }.elsewhen(!txFifo.io.empty && !ftTxeSync) {
        // Write to FT2232H
        dataOut := txFifo.io.dout
        dataOutEn := true.B
        txFifo.io.rd_en := true.B
        io.ftWr := false.B  // Assert write
        state := State.STREAM
      }
    }
    
    is(State.STREAM) {
      dataOutEn := false.B
      io.ftWr := true.B  // Deassert write
      state := State.GET_FIFO
    }
  }
}

/**
 * Simplified FT2232H interface for testability
 * Uses regular I/O instead of bidirectional signals
 */
class FT2232HTestable(rxSize: Int = 64, txSize: Int = 8192) extends Module {
  val io = IO(new Bundle {
    // FT2232H interface (simplified)
    val ftRxf = Input(Bool())
    val ftTxe = Input(Bool())
    val ftDataIn = Input(UInt(16.W))
    val ftDataOut = Output(UInt(16.W))
    val ftDataOutEn = Output(Bool())
    val ftRd = Output(Bool())
    val ftWr = Output(Bool())
    val ftOe = Output(Bool())
    
    // User interface
    val rxData = Output(UInt(16.W))
    val rxValid = Output(Bool())
    val txData = Input(UInt(16.W))
    val txWrite = Input(Bool())
    val txFull = Output(Bool())
  })

  // Default outputs
  io.ftRd := true.B
  io.ftWr := true.B
  io.ftOe := true.B
  io.ftDataOut := 0.U
  io.ftDataOutEn := false.B
  
  // State machine
  object State extends ChiselEnum {
    val GET_FIFO, STREAM = Value
  }
  val state = RegInit(State.GET_FIFO)
  
  // TX FIFO
  val txFifo = Module(new Fifo(width = 16, depth = txSize))
  txFifo.io.din := io.txData
  txFifo.io.wr_en := io.txWrite
  txFifo.io.rd_en := false.B
  io.txFull := txFifo.io.full
  
  // Pipeline stages for FT signals
  val ftRxfSync = ShiftRegister(io.ftRxf, 2)
  val ftTxeSync = ShiftRegister(io.ftTxe, 2)
  
  // RX data capture
  val rxDataReg = RegInit(0.U(16.W))
  val rxValidReg = RegInit(false.B)
  io.rxData := rxDataReg
  io.rxValid := rxValidReg
  
  // Default
  rxValidReg := false.B
  
  switch(state) {
    is(State.GET_FIFO) {
      // Read from FT2232H
      when(!ftRxfSync) {
        io.ftOe := false.B  // Enable output from FT
        io.ftRd := false.B  // Assert read
        state := State.GET_FIFO
        
        // Capture data on next cycle
        rxValidReg := true.B
        rxDataReg := io.ftDataIn
      }.elsewhen(!txFifo.io.empty && !ftTxeSync) {
        // Write to FT2232H
        io.ftDataOut := txFifo.io.dout
        io.ftDataOutEn := true.B
        txFifo.io.rd_en := true.B
        io.ftWr := false.B  // Assert write
        state := State.STREAM
      }
    }
    
    is(State.STREAM) {
      io.ftDataOutEn := false.B
      io.ftWr := true.B  // Deassert write
      state := State.GET_FIFO
    }
  }
}