package retrobus.library.common

import chisel3._
import chisel3.util._

/**
 * Asynchronous FIFO for clock domain crossing
 * Simplified version that uses single clock for now
 * (Real async FIFO would use Chisel's AsyncQueue)
 * 
 * @param width Data width
 * @param depth FIFO depth (must be power of 2)
 */
class AsyncFifo(width: Int = 8, depth: Int = 256) extends Module {
  require(isPow2(depth), "FIFO depth must be a power of 2")
  
  val io = IO(new Bundle {
    val din = Input(UInt(width.W))
    val wr_en = Input(Bool())
    val rd_en = Input(Bool())
    val dout = Output(UInt(width.W))
    val full = Output(Bool())
    val empty = Output(Bool())
  })

  // For now, just use a regular FIFO
  // In a real design, we'd use Chisel's AsyncQueue for proper clock domain crossing
  val fifo = Module(new Fifo(width = width, depth = depth))
  
  fifo.io.din := io.din
  fifo.io.wr_en := io.wr_en
  fifo.io.rd_en := io.rd_en
  io.dout := fifo.io.dout
  io.full := fifo.io.full
  io.empty := fifo.io.empty
}