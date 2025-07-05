package retrobus.library.reset

import chisel3._
import chisel3.util._

/**
 * Reset conditioner module for synchronizing reset signals
 * Migrated from Alchitry Labs reset_conditioner component
 */
class ResetConditioner extends Module {
  val io = IO(new Bundle {
    val in = Input(Bool())    // Raw reset input (active high)
    val out = Output(Bool())  // Conditioned reset output (active high)
  })

  // Shift register for synchronization
  val resetSync = RegInit(VecInit(Seq.fill(4)(true.B)))

  // Combinational logic
  when(io.in) {
    // Asynchronous reset assertion
    resetSync := VecInit(Seq.fill(4)(true.B))
  }.otherwise {
    // Synchronous reset deassertion
    resetSync(0) := false.B
    for (i <- 1 until 4) {
      resetSync(i) := resetSync(i-1)
    }
  }

  // Output is active when any stage is active
  io.out := resetSync.asUInt.orR
}