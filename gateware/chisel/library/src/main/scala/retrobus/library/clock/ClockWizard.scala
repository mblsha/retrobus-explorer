package retrobus.library.clock

import chisel3._
import chisel3.experimental._

/**
 * BlackBox wrapper for Xilinx Clock Wizard IP (clk_wiz_0)
 * Generates 200MHz and 400MHz clocks from 100MHz input
 */
class ClockWizard extends BlackBox {
  val io = IO(new Bundle {
    val clk_in100 = Input(Clock())
    val clk_out200 = Output(Clock())
    val clk_out400 = Output(Clock())
  })
  
  // Match the instance name from the Lucid implementation
  override def desiredName = "clk_wiz_0"
}