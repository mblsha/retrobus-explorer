/**
 * Alchitry Pin Mapping Library
 * 
 * Pin mappings are synchronized with the official Alchitry Labs V2 source:
 * https://github.com/alchitry/Alchitry-Labs-V2/blob/master/src/main/kotlin/com/alchitry/labs2/hardware/pinout/AuPin.kt
 * 
 * When updating this file, please verify mappings against the official source.
 */
package retrobus.library.board

import chisel3._
import chisel3.experimental.{IO, ChiselAnnotation}
import firrtl.annotations.{SingleTargetAnnotation, Target, ModuleTarget, ReferenceTarget}
import scala.io.Source
import scala.util.{Try, Using}
import java.io.{File, PrintWriter}
import scala.collection.mutable

/**
 * Alchitry Virtual Pin to FPGA Pin Mapping
 * 
 * This provides compile-time pin mapping for Alchitry boards,
 * converting virtual pins (like A2, C49) to real FPGA pins.
 * 
 * Pin mappings are derived from the official Alchitry Labs V2 source:
 * https://github.com/alchitry/Alchitry-Labs-V2/blob/master/src/main/kotlin/com/alchitry/labs2/hardware/pinout/AuPin.kt
 */
object AlchitryPinMapper {
  
  // Pin mapping for Alchitry Au board
  // Source: https://github.com/alchitry/Alchitry-Labs-V2/blob/master/src/main/kotlin/com/alchitry/labs2/hardware/pinout/AuPin.kt
  val auPinMap: Map[String, String] = Map(
    // A-bank pins
    "A2" -> "T8", "A3" -> "T7", "A5" -> "T5", "A6" -> "R5",
    "A8" -> "R8", "A9" -> "P8", "A11" -> "L2", "A12" -> "L3",
    "A14" -> "J1", "A15" -> "K1", "A23" -> "K5", "A24" -> "E6",
    "A33" -> "J3", "A34" -> "H3",
    
    // B-bank pins
    "B2" -> "D1", "B3" -> "E2", "B5" -> "A2", "B6" -> "B2",
    "B48" -> "C1", "B49" -> "B1",
    
    // C-bank pins
    "C2" -> "T13", "C3" -> "R13", "C5" -> "T12", "C6" -> "R12",
    "C27" -> "T4", "C28" -> "T3", "C30" -> "R3", "C31" -> "T2",
    "C33" -> "R2", "C34" -> "R1", "C36" -> "N1", "C37" -> "P1",
    "C39" -> "M2", "C40" -> "M1", "C42" -> "N13", "C43" -> "P13",
    "C45" -> "N11", "C46" -> "N12", "C48" -> "P10", "C49" -> "P11",
    
    // D-bank pins
    "D8" -> "R16", "D9" -> "R15", "D43" -> "T15",
    
    // Standard board pins
    "CLOCK" -> "N14", "RESET" -> "P6",
    "LED0" -> "K13", "LED1" -> "K12", "LED2" -> "L14", "LED3" -> "L13",
    "LED4" -> "M16", "LED5" -> "M14", "LED6" -> "M12", "LED7" -> "N16",
    "USB_RX" -> "P16", "USB_TX" -> "P15"
  )
  
  /**
   * Get the real FPGA pin for a virtual pin name.
   * 
   * @param virtualPin Virtual pin name (e.g., "A2", "C49")
   * @param board Board type (currently only "au" supported)
   * @return Real FPGA pin name (e.g., "T8", "P11")
   * 
   * Note: If the virtual pin is not found, returns the original pin name
   * and prints a warning. This allows for forward compatibility if new
   * pins are added to the official Alchitry Labs source.
   */
  def getRealPin(virtualPin: String, board: String = "au"): String = {
    board.toLowerCase match {
      case "au" => auPinMap.getOrElse(virtualPin, {
        println(s"Warning: Virtual pin $virtualPin not found in mapping")
        println(s"Please check the official source and update this mapping if needed:")
        println(s"https://github.com/alchitry/Alchitry-Labs-V2/blob/master/src/main/kotlin/com/alchitry/labs2/hardware/pinout/AuPin.kt")
        virtualPin
      })
      case _ => throw new Exception(s"Unsupported board: $board")
    }
  }
}

/**
 * Pin constraint annotation for Chisel modules
 * Allows specifying virtual pins that get mapped to real pins
 */
case class AlchitryPin(virtualPin: String, board: String = "au") extends ChiselAnnotation {
  def toFirrtl: PinAnnotation = {
    val realPin = AlchitryPinMapper.getRealPin(virtualPin, board)
    PinAnnotation(realPin)
  }
}

case class PinAnnotation(pin: String) extends SingleTargetAnnotation[ReferenceTarget] {
  def duplicate(n: ReferenceTarget): PinAnnotation = this.copy()
}

/**
 * IO Standard annotation
 */
case class IOStandard(standard: String) extends ChiselAnnotation {
  def toFirrtl: IOStandardAnnotation = IOStandardAnnotation(standard)
}

case class IOStandardAnnotation(standard: String) extends SingleTargetAnnotation[ReferenceTarget] {
  def duplicate(n: ReferenceTarget): IOStandardAnnotation = this.copy()
}

/**
 * Alchitry board base class with automatic pin mapping
 */
abstract class AlchitryModule(board: String = "au") extends Module {
  
  // Helper method to assign virtual pins
  def assignPin(port: Data, virtualPin: String): Unit = {
    port match {
      case b: Bool => b.addAttribute("alchitry_pin", virtualPin)
      case v: Vec[_] => 
        // Handle vector pins
        println(s"Warning: Cannot assign single pin $virtualPin to vector port")
      case _ =>
        println(s"Warning: Unsupported port type for pin assignment")
    }
  }
  
  // Helper to assign pin with IO standard
  def assignPin(port: Data, virtualPin: String, ioStandard: String): Unit = {
    assignPin(port, virtualPin)
    port.addAttribute("io_standard", ioStandard)
  }
}

/**
 * Constraint file generator for Alchitry boards
 */
object AlchitryConstraintGenerator {
  
  case class PinConstraint(
    portName: String,
    virtualPin: String,
    realPin: String,
    ioStandard: String = "LVCMOS33",
    pullup: Boolean = false,
    pulldown: Boolean = false
  )
  
  def generateXDC(
    moduleName: String,
    constraints: Seq[PinConstraint],
    outputFile: String,
    board: String = "au"
  ): Unit = {
    val writer = new PrintWriter(new File(outputFile))
    
    try {
      writer.println(s"# $moduleName Constraint File for Alchitry ${board.toUpperCase}")
      writer.println("# Generated by AlchitryConstraintGenerator")
      writer.println(s"# Date: ${java.time.LocalDateTime.now}")
      writer.println()
      
      // Group constraints by category
      val groupedConstraints = constraints.groupBy { c =>
        if (c.portName.contains("clk")) "Clock"
        else if (c.portName.contains("rst")) "Reset"
        else if (c.portName.contains("led")) "LEDs"
        else if (c.portName.contains("usb")) "USB UART"
        else "User I/O"
      }
      
      groupedConstraints.foreach { case (group, pins) =>
        writer.println(s"# $group")
        pins.foreach { constraint =>
          // Package pin
          writer.println(s"set_property PACKAGE_PIN ${constraint.realPin} [get_ports ${constraint.portName}]")
          
          // IO Standard
          writer.println(s"set_property IOSTANDARD ${constraint.ioStandard} [get_ports ${constraint.portName}]")
          
          // Pull-up/down if needed
          if (constraint.pullup) {
            writer.println(s"set_property PULLUP TRUE [get_ports ${constraint.portName}]")
          }
          if (constraint.pulldown) {
            writer.println(s"set_property PULLDOWN TRUE [get_ports ${constraint.portName}]")
          }
        }
        writer.println()
      }
      
      // Add clock constraint if present
      constraints.find(_.portName.contains("clk")).foreach { clkConstraint =>
        writer.println("# Clock constraint")
        writer.println(s"create_clock -period 10.000 -name ${clkConstraint.portName} [get_ports ${clkConstraint.portName}]")
      }
      
    } finally {
      writer.close()
    }
    
    println(s"Generated constraint file: $outputFile")
  }
}

/**
 * Mix-in trait for automatic constraint generation
 */
trait AlchitryConstraints { self: Module =>
  
  private val pinConstraints = mutable.ListBuffer[AlchitryConstraintGenerator.PinConstraint]()
  
  def mapPin(port: Data, virtualPin: String, ioStandard: String = "LVCMOS33"): Unit = {
    val portName = port.pathName
    val realPin = AlchitryPinMapper.getRealPin(virtualPin)
    
    pinConstraints += AlchitryConstraintGenerator.PinConstraint(
      portName = portName,
      virtualPin = virtualPin,
      realPin = realPin,
      ioStandard = ioStandard
    )
  }
  
  def mapPins(ports: Seq[(Data, String)]): Unit = {
    ports.foreach { case (port, pin) => mapPin(port, pin) }
  }
  
  def generateConstraints(outputFile: String): Unit = {
    AlchitryConstraintGenerator.generateXDC(
      moduleName = this.name,
      constraints = pinConstraints.toSeq,
      outputFile = outputFile
    )
  }
}