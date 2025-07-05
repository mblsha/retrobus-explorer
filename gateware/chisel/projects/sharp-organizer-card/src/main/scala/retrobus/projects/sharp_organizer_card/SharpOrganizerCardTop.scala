package retrobus.projects.sharp_organizer_card

import chisel3._
import circt.stage.ChiselStage

/**
 * Top-level object for generating Verilog from SharpOrganizerCard
 */
object SharpOrganizerCardTop extends App {
  (new ChiselStage).execute(
    Array("--target", "systemverilog", "--split-verilog"),
    Seq(
      chisel3.stage.ChiselGeneratorAnnotation(() => new SharpOrganizerCard)
    )
  )
}