package retrobus.projects.pin_tester

import chisel3._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec

/**
 * Comprehensive test suite for pin-tester project
 * 
 * This combines all the basic tests into a comprehensive suite that:
 * - Tests all major functionality
 * - Provides clear pass/fail reporting  
 * - Can be run as a complete regression test
 * - Serves as documentation of expected behavior
 */
class PinTesterTestSuite extends AnyFlatSpec with ChiselScalatestTester {

  // Test configuration
  val TEST_TIMEOUT = 10000 // cycles

  behavior of "PinTester Complete Functionality"

  it should "pass all initialization and basic functionality tests" in {
    test(new PinTesterTestable).withAnnotations(Seq(WriteVcdAnnotation)) { dut =>
      
      println("=== PIN TESTER COMPREHENSIVE TEST SUITE ===")
      
      // Test 1: Initialization
      println("\n1. Testing initialization...")
      dut.io.usb_rx.poke(true.B)
      dut.io.ffc_data_in.poke(0.U)
      dut.io.rst_n.poke(false.B)
      dut.clock.step(10)
      dut.io.rst_n.poke(true.B)
      dut.clock.step(50)
      
      // Should start in RECEIVE mode
      dut.io.ffc_data_oe.expect(false.B)
      dut.io.led.expect(0.U)
      dut.io.saleae.expect(0.U)
      println("✓ Initialization test passed")
      
      // Test 2: RECEIVE mode data display
      println("\n2. Testing RECEIVE mode data display...")
      val testData = "h123456789ABCDEF".U(48.W)
      dut.io.ffc_data_in.poke(testData)
      dut.clock.step(10)
      
      // Bank 0 should show bits 7:0 = 0xEF
      dut.io.led.expect(0xEF.U)
      dut.io.saleae.expect(0xEF.U)
      dut.io.ffc_data_oe.expect(false.B)
      println("✓ RECEIVE mode data display test passed")
      
      // Test 3: ffc_data patterns
      println("\n3. Testing various ffc_data input patterns...")
      val patterns = Seq(
        ("h000000000000", 0x00),
        ("hFFFFFFFFFFFF", 0xFF),
        ("hAAAAAAAAAAAA", 0xAA),
        ("h555555555555", 0x55)
      )
      
      for ((pattern, expectedLed) <- patterns) {
        dut.io.ffc_data_in.poke(pattern.U(48.W))
        dut.clock.step(5)
        dut.io.led.expect(expectedLed.U)
        dut.io.saleae.expect(expectedLed.U)
      }
      println("✓ ffc_data pattern test passed")
      
      // Test 4: Reset behavior during operation
      println("\n4. Testing reset behavior...")
      dut.io.ffc_data_in.poke("hDEADBEEF1234".U(48.W))
      dut.clock.step(10)
      
      // Apply reset
      dut.io.rst_n.poke(false.B)
      dut.clock.step(5)
      dut.io.ffc_data_oe.expect(false.B) // Should not drive during reset
      
      // Release reset  
      dut.io.rst_n.poke(true.B)
      dut.clock.step(10)
      dut.io.ffc_data_oe.expect(false.B) // Should return to RECEIVE mode
      println("✓ Reset behavior test passed")
      
      // Test 5: Clock domain stability
      println("\n5. Testing clock domain stability...")
      dut.io.ffc_data_in.poke("h123456789ABC".U(48.W))
      
      // Run for many cycles and ensure stable operation
      for (cycle <- 0 until 100) {
        dut.clock.step(1)
        
        // Should maintain consistent behavior
        dut.io.led.expect(0xBC.U) // Bits 7:0 of test pattern
        dut.io.saleae.expect(0xBC.U)
        dut.io.ffc_data_oe.expect(false.B)
        
        if (cycle % 25 == 0) {
          println(f"  Cycle $cycle: LED=0x${dut.io.led.peek().litValue}%02X, stable")
        }
      }
      println("✓ Clock domain stability test passed")
      
      // Test 6: Signal integrity
      println("\n6. Testing signal integrity...")
      
      // Test all LED bits
      for (bitPattern <- 0 until 256) {
        val testValue = f"h${bitPattern}%02X${"00" * 5}".U(48.W)
        dut.io.ffc_data_in.poke(testValue)
        dut.clock.step(2)
        dut.io.led.expect(bitPattern.U)
        dut.io.saleae.expect(bitPattern.U)
      }
      println("✓ Signal integrity test passed")
      
      // Test 7: Boundary conditions
      println("\n7. Testing boundary conditions...")
      
      // Maximum values
      dut.io.ffc_data_in.poke("hFFFFFFFFFFFF".U(48.W))
      dut.clock.step(5)
      dut.io.led.expect(0xFF.U)
      
      // Minimum values  
      dut.io.ffc_data_in.poke(0.U)
      dut.clock.step(5)
      dut.io.led.expect(0.U)
      
      // Alternating patterns
      dut.io.ffc_data_in.poke("hAAAAAAAAAA".U(48.W))
      dut.clock.step(5)
      dut.io.led.expect(0xAA.U)
      
      println("✓ Boundary conditions test passed")
      
      println("\n=== ALL TESTS PASSED ===")
      println("Pin-tester basic functionality is working correctly!")
      println("\nTest Summary:")
      println("✓ Initialization and reset")
      println("✓ RECEIVE mode data display") 
      println("✓ Input data patterns")
      println("✓ Reset behavior")
      println("✓ Clock domain stability")
      println("✓ Signal integrity")
      println("✓ Boundary conditions")
      println("\nNote: UART command testing requires the advanced UART test suite")
    }
  }

  it should "demonstrate expected waveforms" in {
    test(new PinTesterTestable).withAnnotations(Seq(WriteVcdAnnotation)) { dut =>
      
      println("\n=== WAVEFORM DEMONSTRATION ===")
      
      // Initialize
      dut.io.usb_rx.poke(true.B)
      dut.io.rst_n.poke(false.B)
      dut.clock.step(5)
      dut.io.rst_n.poke(true.B)
      dut.clock.step(10)
      
      // Create interesting waveforms for VCD analysis
      val testSequence = Seq(
        "h123456789ABC",
        "h000000000000", 
        "hFFFFFFFFFFFF",
        "hAAAAAAAAAAAA",
        "h555555555555",
        "hDEADBEEF1234",
        "h987654321098"
      )
      
      for ((pattern, index) <- testSequence.zipWithIndex) {
        println(f"Setting pattern $index: $pattern")
        dut.io.ffc_data_in.poke(pattern.U(48.W))
        dut.clock.step(20) // Hold each pattern for 20 cycles
        
        // Log the output for verification
        val ledValue = dut.io.led.peek().litValue
        val saleaeValue = dut.io.saleae.peek().litValue
        println(f"  LED output: 0x$ledValue%02X, Saleae: 0x$saleaeValue%02X")
      }
      
      println("✓ Waveform demonstration complete")
      println("Check the generated VCD file for detailed timing analysis")
    }
  }
}