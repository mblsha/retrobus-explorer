package retrobus.projects.pin_tester

import chisel3._
import chisel3.util._
import retrobus.library.reset.ResetConditioner
import retrobus.library.uart.{UartRx, UartTx}
import retrobus.library.board.{AlchitryConstraints, AlchitryPinMapper}

/**
 * Pin Tester with integrated Alchitry pin mapping
 * This version automatically generates constraint files with proper pin mappings
 */
class PinTesterWithPins extends AlchitryTop with AlchitryConstraints {
  
  override def desiredName = "PinTester"
  
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
  
  // Saleae debug outputs - using B bank pins
  val saleaePins = Seq("B8", "B9", "B11", "B12", "B39", "B40", "D11", "D12")
  // Would map individual bits if exposed as separate signals
  
  // FFC 48-bit data bus - organized in 6 banks of 8 bits
  // These mappings follow the level-shifter board layout
  val ffcDataPins = Seq(
    // Bank 0 (bits 0-7)
    "A49", "A48", "A46", "A45", "A2", "A3", "A5", "A6",
    // Bank 1 (bits 8-15)
    "C2", "C3", "C5", "C6", "C49", "C48", "C46", "C45",
    // Bank 2 (bits 16-23)
    "A8", "A9", "A11", "A12", "A14", "A15", "A23", "A24",
    // Bank 3 (bits 24-31)
    "C43", "C42", "C40", "C39", "C37", "C36", "C34", "C33",
    // Bank 4 (bits 32-39)
    "A34", "A33", "B49", "B48", "B2", "B3", "B5", "B6",
    // Bank 5 (bits 40-47)
    "C31", "C30", "C28", "C27", "D8", "D9", "D43", "D42"
  )
  
  // Document the pin mappings
  println("// FFC Data Pin Mappings:")
  ffcDataPins.zipWithIndex.foreach { case (pin, i) =>
    val realPin = AlchitryPinMapper.getRealPin(pin)
    println(s"// io_ffc_data[$i] -> $pin (real: $realPin)")
  }
  
  saleaePins.zipWithIndex.foreach { case (pin, i) =>
    val realPin = AlchitryPinMapper.getRealPin(pin)
    println(s"// io_saleae[$i] -> $pin (real: $realPin)")
  }
}

/**
 * Companion object for elaboration with constraint generation
 */
object PinTesterWithPins extends App {
  import retrobus.library.board.AlchitryElaborator
  import retrobus.library.board.AlchitryElaborator._
  
  // Define complete pin mappings
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
    
    // Saleae debug
    PinMapping("io_saleae[0]", "B8"),
    PinMapping("io_saleae[1]", "B9"),
    PinMapping("io_saleae[2]", "B11"),
    PinMapping("io_saleae[3]", "B12"),
    PinMapping("io_saleae[4]", "B39"),
    PinMapping("io_saleae[5]", "B40"),
    PinMapping("io_saleae[6]", "D11"),
    PinMapping("io_saleae[7]", "D12")
  ) ++ 
  // FFC data pins - all 48 bits
  Seq(
    // Bank 0 (bits 0-7)
    PinMapping("io_ffc_data[0]", "A49"),
    PinMapping("io_ffc_data[1]", "A48"),
    PinMapping("io_ffc_data[2]", "A46"),
    PinMapping("io_ffc_data[3]", "A45"),
    PinMapping("io_ffc_data[4]", "A2"),
    PinMapping("io_ffc_data[5]", "A3"),
    PinMapping("io_ffc_data[6]", "A5"),
    PinMapping("io_ffc_data[7]", "A6"),
    // Bank 1 (bits 8-15)
    PinMapping("io_ffc_data[8]", "C2"),
    PinMapping("io_ffc_data[9]", "C3"),
    PinMapping("io_ffc_data[10]", "C5"),
    PinMapping("io_ffc_data[11]", "C6"),
    PinMapping("io_ffc_data[12]", "C49"),
    PinMapping("io_ffc_data[13]", "C48"),
    PinMapping("io_ffc_data[14]", "C46"),
    PinMapping("io_ffc_data[15]", "C45"),
    // Bank 2 (bits 16-23)
    PinMapping("io_ffc_data[16]", "A8"),
    PinMapping("io_ffc_data[17]", "A9"),
    PinMapping("io_ffc_data[18]", "A11"),
    PinMapping("io_ffc_data[19]", "A12"),
    PinMapping("io_ffc_data[20]", "A14"),
    PinMapping("io_ffc_data[21]", "A15"),
    PinMapping("io_ffc_data[22]", "A23"),
    PinMapping("io_ffc_data[23]", "A24"),
    // Bank 3 (bits 24-31)
    PinMapping("io_ffc_data[24]", "C43"),
    PinMapping("io_ffc_data[25]", "C42"),
    PinMapping("io_ffc_data[26]", "C40"),
    PinMapping("io_ffc_data[27]", "C39"),
    PinMapping("io_ffc_data[28]", "C37"),
    PinMapping("io_ffc_data[29]", "C36"),
    PinMapping("io_ffc_data[30]", "C34"),
    PinMapping("io_ffc_data[31]", "C33"),
    // Bank 4 (bits 32-39)
    PinMapping("io_ffc_data[32]", "A34"),
    PinMapping("io_ffc_data[33]", "A33"),
    PinMapping("io_ffc_data[34]", "B49"),
    PinMapping("io_ffc_data[35]", "B48"),
    PinMapping("io_ffc_data[36]", "B2"),
    PinMapping("io_ffc_data[37]", "B3"),
    PinMapping("io_ffc_data[38]", "B5"),
    PinMapping("io_ffc_data[39]", "B6"),
    // Bank 5 (bits 40-47)
    PinMapping("io_ffc_data[40]", "C31"),
    PinMapping("io_ffc_data[41]", "C30"),
    PinMapping("io_ffc_data[42]", "C28"),
    PinMapping("io_ffc_data[43]", "C27"),
    PinMapping("io_ffc_data[44]", "D8"),
    PinMapping("io_ffc_data[45]", "D9"),
    PinMapping("io_ffc_data[46]", "D43"),
    PinMapping("io_ffc_data[47]", "D42")
  )
  
  // Generate Verilog and constraints
  AlchitryElaborator.elaborate(
    gen = new PinTesterWithPins,
    pinMappings = pinMappings,
    board = "au",
    targetDir = "generated/pin-tester",
    moduleName = Some("PinTester")
  )
}