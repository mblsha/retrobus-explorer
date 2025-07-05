package retrobus.library.common

import chisel3._
import chisel3.util._

/**
 * Edge detector for finding rising and falling edges in signals
 * 
 * @param stagesParam Number of pipeline stages for detection (default 3)
 */
class EdgeDetector(stagesParam: Int = 3) extends Module {
  val io = IO(new Bundle {
    val in = Input(Bool())
    val out = Output(Bool())
    val outRising = Output(Bool())
    val outFalling = Output(Bool())
  })

  // Create a shift register for edge detection
  val stages = RegInit(VecInit(Seq.fill(stagesParam)(false.B)))
  
  // Shift in new values
  stages(0) := io.in
  for (i <- 1 until stagesParam) {
    stages(i) := stages(i - 1)
  }
  
  // Edge detection logic
  val rising = stages(stagesParam - 2) && !stages(stagesParam - 1)
  val falling = !stages(stagesParam - 2) && stages(stagesParam - 1)
  val changed = stages(stagesParam - 2) =/= stages(stagesParam - 1)
  
  io.out := changed
  io.outRising := rising
  io.outFalling := falling
}