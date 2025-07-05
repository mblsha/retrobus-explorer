package retrobus.library.common

import chisel3._
import chisel3.util._

/**
 * Pipeline (synchronizer) for clock domain crossing
 * Creates a chain of registers to synchronize signals
 * 
 * @param width Width of the signal to synchronize
 * @param stagesParam Number of synchronization stages (default 2)
 */
class Pipeline(width: Int = 1, stagesParam: Int = 2) extends Module {
  val io = IO(new Bundle {
    val in = Input(UInt(width.W))
    val out = Output(UInt(width.W))
  })

  // Create pipeline registers
  val stages = RegInit(VecInit(Seq.fill(stagesParam)(0.U(width.W))))
  
  // Connect pipeline
  stages(0) := io.in
  for (i <- 1 until stagesParam) {
    stages(i) := stages(i - 1)
  }
  
  io.out := stages(stagesParam - 1)
}