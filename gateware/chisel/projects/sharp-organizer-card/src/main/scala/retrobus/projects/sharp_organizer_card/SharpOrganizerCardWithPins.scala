package retrobus.projects.sharp_organizer_card

import chisel3._
import chisel3.util._
import retrobus.library.reset.ResetConditioner
import retrobus.library.uart._
import retrobus.library.common._
import retrobus.library.ft.FT2232HTestable
import retrobus.library.clock.ClockWizard
import retrobus.library.board.{AlchitryConstraints, AlchitryPinMapper}

/**
 * Sharp Organizer Card with integrated Alchitry pin mapping
 * This version automatically generates constraint files with proper pin mappings
 */
class SharpOrganizerCardWithPins extends SharpOrganizerCard with AlchitryConstraints {
  
  // Define pin mappings using virtual Alchitry pins
  override def desiredName = "SharpOrganizerCard"
  
  // System pins
  mapPin(io.clk, "CLOCK")
  mapPin(io.rst_n, "RESET")
  
  // LEDs - use standard LED pins
  io.led.asBools.zipWithIndex.foreach { case (led, i) =>
    mapPin(led, s"LED$i")
  }
  
  // USB UART
  mapPin(io.usb_rx, "USB_RX")
  mapPin(io.usb_tx, "USB_TX")
  
  // Address bus (20 bits) - using virtual pins
  val addrPins = Seq(
    "C39", "C37", "C36", "C34", "C33",  // addr[0-4]
    "A34", "A33", "B49", "B48", "B2",   // addr[5-9]
    "B3", "B5", "B6", "C31", "C30",     // addr[10-14]
    "C28", "C3", "C5", "C6", "C49"      // addr[15-19]
  )
  
  // Map address bits if exposed as individual signals
  // Note: The current implementation has addr as a single UInt, 
  // so we'll need to handle this differently
  
  // Data bus (8 bits) - using virtual pins
  val dataPins = Seq(
    "C40", "C42", "C43", "A24", "A23", "A15", "A14", "A12"
  )
  
  // Control signals
  mapPin(io.conn_rw, "C46", "LVCMOS33", pullup = true)
  mapPin(io.conn_oe, "C48", "LVCMOS33", pullup = true)
  mapPin(io.conn_ci, "C2", "LVCMOS33", pullup = true)
  mapPin(io.conn_e2, "A6", "LVCMOS33", pullup = true)
  
  // Memory bank signals
  mapPin(io.conn_mskrom, "A11", "LVCMOS33", pullup = true)
  mapPin(io.conn_sram1, "A9", "LVCMOS33", pullup = true)
  mapPin(io.conn_sram2, "A8", "LVCMOS33", pullup = true)
  mapPin(io.conn_eprom, "C45", "LVCMOS33", pullup = true)
  
  // Power control signals
  mapPin(io.conn_stnby, "D9", "LVCMOS33", pullup = true)
  mapPin(io.conn_vbatt, "D8", "LVCMOS33", pullup = true)
  mapPin(io.conn_vpp, "C27", "LVCMOS33", pullup = true)
  
  // FT2232H interface pins (these would need proper mapping)
  // Note: These are placeholder mappings - need actual board pins
  mapPin(io.ft_clk, "B13")
  mapPin(io.ft_rxf, "B33")  
  mapPin(io.ft_txe, "B15")
  mapPin(io.ft_rd, "C11")
  mapPin(io.ft_wr, "C12")
  mapPin(io.ft_oe, "C15")
  
  // Saleae debug outputs - using available pins
  val saleaePins = Seq("A27", "A28", "A30", "A31", "A36", "A37", "A39", "A40")
  // Would need to map individual bits if exposed
  
  // For bus signals, we need a helper method
  def mapBusPin(busName: String, bit: Int, virtualPin: String, pullup: Boolean = false): Unit = {
    // This would map individual bits of a bus
    // For now, document the mapping in comments
    println(s"// $busName[$bit] -> $virtualPin (real: ${AlchitryPinMapper.getRealPin(virtualPin)})")
  }
  
  // Document bus mappings
  addrPins.zipWithIndex.foreach { case (pin, i) =>
    mapBusPin("io_addr", i, pin, pullup = true)
  }
  
  dataPins.zipWithIndex.foreach { case (pin, i) =>
    mapBusPin("io_data", i, pin, pullup = true)
  }
}

/**
 * Companion object for elaboration with constraint generation
 */
object SharpOrganizerCardWithPins extends App {
  import retrobus.library.board.AlchitryElaborator
  import retrobus.library.board.AlchitryElaborator._
  
  // Define complete pin mappings including bus signals
  val pinMappings = Seq(
    // System
    PinMapping("io_clk", "CLOCK"),
    PinMapping("io_rst_n", "RESET"),
    
    // LEDs
    PinMapping("io_led[0]", "LED0"),
    PinMapping("io_led[1]", "LED1"),
    PinMapping("io_led[2]", "LED2"),
    PinMapping("io_led[3]", "LED3"),
    PinMapping("io_led[4]", "LED4"),
    PinMapping("io_led[5]", "LED5"),
    PinMapping("io_led[6]", "LED6"),
    PinMapping("io_led[7]", "LED7"),
    
    // USB UART
    PinMapping("io_usb_rx", "USB_RX"),
    PinMapping("io_usb_tx", "USB_TX"),
    
    // Address bus - individual bits
    PinMapping("io_addr[0]", "C39", pullup = true),
    PinMapping("io_addr[1]", "C37", pullup = true),
    PinMapping("io_addr[2]", "C36", pullup = true),
    PinMapping("io_addr[3]", "C34", pullup = true),
    PinMapping("io_addr[4]", "C33", pullup = true),
    PinMapping("io_addr[5]", "A34", pullup = true),
    PinMapping("io_addr[6]", "A33", pullup = true),
    PinMapping("io_addr[7]", "B49", pullup = true),
    PinMapping("io_addr[8]", "B48", pullup = true),
    PinMapping("io_addr[9]", "B2", pullup = true),
    PinMapping("io_addr[10]", "B3", pullup = true),
    PinMapping("io_addr[11]", "B5", pullup = true),
    PinMapping("io_addr[12]", "B6", pullup = true),
    PinMapping("io_addr[13]", "C31", pullup = true),
    PinMapping("io_addr[14]", "C30", pullup = true),
    PinMapping("io_addr[15]", "C28", pullup = true),
    PinMapping("io_addr[16]", "C3", pullup = true),
    PinMapping("io_addr[17]", "C5", pullup = true),
    PinMapping("io_addr[18]", "C6", pullup = true),
    PinMapping("io_addr[19]", "C49", pullup = true),
    
    // Data bus
    PinMapping("io_data[0]", "C40", pullup = true),
    PinMapping("io_data[1]", "C42", pullup = true),
    PinMapping("io_data[2]", "C43", pullup = true),
    PinMapping("io_data[3]", "A24", pullup = true),
    PinMapping("io_data[4]", "A23", pullup = true),
    PinMapping("io_data[5]", "A15", pullup = true),
    PinMapping("io_data[6]", "A14", pullup = true),
    PinMapping("io_data[7]", "A12", pullup = true),
    
    // Control signals
    PinMapping("io_conn_rw", "C46", pullup = true),
    PinMapping("io_conn_oe", "C48", pullup = true),
    PinMapping("io_conn_ci", "C2", pullup = true),
    PinMapping("io_conn_e2", "A6", pullup = true),
    
    // Memory bank signals
    PinMapping("io_conn_mskrom", "A11", pullup = true),
    PinMapping("io_conn_sram1", "A9", pullup = true),
    PinMapping("io_conn_sram2", "A8", pullup = true),
    PinMapping("io_conn_eprom", "C45", pullup = true),
    
    // Power signals
    PinMapping("io_conn_stnby", "D9", pullup = true),
    PinMapping("io_conn_vbatt", "D8", pullup = true),
    PinMapping("io_conn_vpp", "C27", pullup = true)
  )
  
  // Generate Verilog and constraints
  AlchitryElaborator.elaborate(
    gen = new SharpOrganizerCardWithPins,
    pinMappings = pinMappings,
    board = "au",
    targetDir = "generated/sharp-organizer-card",
    moduleName = Some("SharpOrganizerCard")
  )
}