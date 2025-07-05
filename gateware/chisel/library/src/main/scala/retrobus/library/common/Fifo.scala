package retrobus.library.common

import chisel3._
import chisel3.util._

/**
 * Simple FIFO implementation
 * 
 * @param width Data width
 * @param depth FIFO depth (must be power of 2)
 */
class Fifo(width: Int = 8, depth: Int = 256) extends Module {
  require(isPow2(depth), "FIFO depth must be a power of 2")
  
  val io = IO(new Bundle {
    val din = Input(UInt(width.W))
    val wr_en = Input(Bool())
    val rd_en = Input(Bool())
    val dout = Output(UInt(width.W))
    val full = Output(Bool())
    val empty = Output(Bool())
  })

  val addrBits = log2Ceil(depth)
  
  // Memory
  val mem = SyncReadMem(depth, UInt(width.W))
  
  // Pointers
  val wrPtr = RegInit(0.U(addrBits.W))
  val rdPtr = RegInit(0.U(addrBits.W))
  
  // Status
  val empty = RegInit(true.B)
  val full = RegInit(false.B)
  
  // Write logic
  when(io.wr_en && !full) {
    mem.write(wrPtr, io.din)
    wrPtr := wrPtr + 1.U
  }
  
  // Read logic
  val dout = RegInit(0.U(width.W))
  when(io.rd_en && !empty) {
    dout := mem.read(rdPtr)
    rdPtr := rdPtr + 1.U
  }
  
  // Update status flags
  val nextWrPtr = wrPtr + 1.U
  val nextRdPtr = rdPtr + 1.U
  
  when(io.wr_en && !io.rd_en && !full) {
    empty := false.B
    when(nextWrPtr === rdPtr) {
      full := true.B
    }
  }.elsewhen(!io.wr_en && io.rd_en && !empty) {
    full := false.B
    when(nextRdPtr === wrPtr) {
      empty := true.B
    }
  }.elsewhen(io.wr_en && io.rd_en) {
    when(full) {
      full := false.B
    }
    when(empty) {
      empty := false.B
    }
  }
  
  // Outputs
  io.dout := dout
  io.full := full
  io.empty := empty
}