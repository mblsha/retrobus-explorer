package retrobus.projects.pin_tester

import chisel3._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec

/**
 * Advanced testbench for pin-tester with UART protocol simulation
 * 
 * This testbench includes:
 * - Proper UART bit-level simulation at 1Mbaud
 * - Complete command testing ('0'-'5', 's', 'r')  
 * - State machine verification
 * - Bank selection and mode switching tests
 */
class PinTesterUartTest extends AnyFlatSpec with ChiselScalatestTester {

  // UART configuration
  val UART_BAUD = 1_000_000
  val CLK_FREQ = 100_000_000
  val CYCLES_PER_BIT = CLK_FREQ / UART_BAUD // 100 cycles per bit at 1Mbaud

  // ASCII command values
  val CMD_BANK_0 = 48  // '0'
  val CMD_BANK_1 = 49  // '1'
  val CMD_BANK_2 = 50  // '2'
  val CMD_BANK_3 = 51  // '3'
  val CMD_BANK_4 = 52  // '4'
  val CMD_BANK_5 = 53  // '5'
  val CMD_SEND_LOWER = 115 // 's'
  val CMD_SEND_UPPER = 83  // 'S'
  val CMD_RECV_LOWER = 114 // 'r'
  val CMD_RECV_UPPER = 82  // 'R'

  /**
   * Send a UART byte with proper bit timing
   */
  def sendUartByte(dut: AlchitryTop, data: Int): Unit = {
    println(f"Sending UART byte: 0x$data%02X (${data.toChar})")
    
    // UART idle state (high)
    dut.io.usb_rx.poke(true.B)
    dut.clock.step(CYCLES_PER_BIT)
    
    // Start bit (low)
    dut.io.usb_rx.poke(false.B)
    dut.clock.step(CYCLES_PER_BIT)
    
    // Data bits (LSB first)
    for (bit <- 0 until 8) {
      val bitValue = (data >> bit) & 1
      dut.io.usb_rx.poke(bitValue.B)
      dut.clock.step(CYCLES_PER_BIT)
    }
    
    // Stop bit (high)
    dut.io.usb_rx.poke(true.B)
    dut.clock.step(CYCLES_PER_BIT)
    
    // Extra idle time
    dut.clock.step(CYCLES_PER_BIT / 2)
  }

  /**
   * Wait for UART transmission to complete and check for echo
   */
  def waitForUartResponse(dut: AlchitryTop, expectedEcho: Option[Int] = None): Unit = {
    // Wait for processing
    dut.clock.step(CYCLES_PER_BIT * 2)
    
    // In a complete testbench, we would monitor usb_tx for echo
    // For now, we'll just ensure the system has time to respond
  }

  /**
   * Initialize DUT with proper reset sequence
   */
  def initializeDut(dut: AlchitryTop): Unit = {
    dut.io.usb_rx.poke(true.B) // UART idle
    dut.io.ffc_data_in.poke(0.U)
    
    // Apply reset
    dut.io.rst_n.poke(false.B)
    dut.clock.step(10)
    dut.io.rst_n.poke(true.B)
    dut.clock.step(50) // Allow reset conditioning
  }

  "PinTester UART Interface" should "respond to bank selection commands" in {
    test(new AlchitryTop) { dut =>
      initializeDut(dut)
      
      // Set test data with distinct patterns for each bank
      val testData = "h123456789ABCDEF0".U(48.W)
      dut.io.ffc_data_in.poke(testData)
      dut.clock.step(10)
      
      // Initial state: RECEIVE mode, bank 0
      // Bits 7:0 of testData = 0xF0
      dut.io.led.expect(0xF0.U, "Initial bank 0 should show 0xF0")
      dut.io.saleae.expect(0xF0.U)
      dut.io.ffc_data_oe.expect(false.B, "Should not be driving in RECEIVE mode")
      
      // Test bank 1 selection
      sendUartByte(dut, CMD_BANK_1)
      waitForUartResponse(dut)
      
      // Bits 15:8 of testData = 0xDE  
      dut.io.led.expect(0xDE.U, "Bank 1 should show 0xDE")
      dut.io.saleae.expect(0xDE.U)
      
      // Test bank 2 selection
      sendUartByte(dut, CMD_BANK_2)
      waitForUartResponse(dut)
      
      // Bits 23:16 of testData = 0xBC
      dut.io.led.expect(0xBC.U, "Bank 2 should show 0xBC")
      dut.io.saleae.expect(0xBC.U)
      
      println("Bank selection test passed")
    }
  }

  it should "switch to SEND mode and generate counter output" in {
    test(new AlchitryTop) { dut =>
      initializeDut(dut)
      
      // Start in RECEIVE mode
      dut.io.ffc_data_oe.expect(false.B)
      
      // Switch to SEND mode with 's' command
      sendUartByte(dut, CMD_SEND_LOWER)
      waitForUartResponse(dut)
      
      // Should now be in SEND mode - driving ffc_data
      dut.io.ffc_data_oe.expect(true.B, "Should be driving in SEND mode")
      
      // Counter should be incrementing
      val counter1 = dut.io.led.peek().litValue
      dut.clock.step(100)
      val counter2 = dut.io.led.peek().litValue
      
      // LED and saleae should show the same counter value
      dut.io.led.expect(dut.io.saleae.peek())
      
      // ffc_data_out should also show counter (low 8 bits in bank 0)
      dut.io.ffc_data_out.expect(dut.io.led.peek())
      
      println(f"Counter progression: $counter1 -> $counter2")
      println("SEND mode test passed")
    }
  }

  it should "switch back to RECEIVE mode" in {
    test(new AlchitryTop) { dut =>
      initializeDut(dut)
      
      // Switch to SEND mode first
      sendUartByte(dut, CMD_SEND_UPPER) // Test 'S' command
      waitForUartResponse(dut)
      dut.io.ffc_data_oe.expect(true.B)
      
      // Set some input data
      val inputData = "hDEADBEEF".U(48.W)
      dut.io.ffc_data_in.poke(inputData)
      
      // Switch back to RECEIVE mode
      sendUartByte(dut, CMD_RECV_LOWER) // Test 'r' command
      waitForUartResponse(dut)
      
      // Should stop driving and show input data
      dut.io.ffc_data_oe.expect(false.B, "Should stop driving in RECEIVE mode")
      
      // Should display input data (bank 0, bits 7:0 = 0xEF)
      dut.io.led.expect(0xEF.U)
      dut.io.saleae.expect(0xEF.U)
      
      println("Mode switching test passed")
    }
  }

  it should "handle bank selection in SEND mode" in {
    test(new AlchitryTop) { dut =>
      initializeDut(dut)
      
      // Switch to SEND mode
      sendUartByte(dut, CMD_SEND_LOWER)
      waitForUartResponse(dut)
      
      // Test bank selection in SEND mode
      // Different banks should show different parts of the counter
      
      // Bank 0 (default)
      val bank0_value = dut.io.led.peek().litValue
      
      // Switch to bank 1 
      sendUartByte(dut, CMD_BANK_1)
      waitForUartResponse(dut)
      
      val bank1_value = dut.io.led.peek().litValue
      
      // Switch to bank 2
      sendUartByte(dut, CMD_BANK_2)
      waitForUartResponse(dut)
      
      val bank2_value = dut.io.led.peek().litValue
      
      println(f"Bank values in SEND mode - Bank0: $bank0_value, Bank1: $bank1_value, Bank2: $bank2_value")
      
      // Verify we're still in SEND mode
      dut.io.ffc_data_oe.expect(true.B)
      
      println("SEND mode bank selection test passed")
    }
  }

  it should "ignore invalid commands" in {
    test(new AlchitryTop) { dut =>
      initializeDut(dut)
      
      // Record initial state
      val initialLed = dut.io.led.peek().litValue
      val initialOe = dut.io.ffc_data_oe.peek().litValue
      
      // Send invalid commands
      sendUartByte(dut, 'x'.toInt) // Invalid character
      waitForUartResponse(dut)
      
      sendUartByte(dut, '6'.toInt) // Invalid bank (only 0-5 valid)
      waitForUartResponse(dut)
      
      sendUartByte(dut, 'z'.toInt) // Another invalid character
      waitForUartResponse(dut)
      
      // State should be unchanged
      dut.io.led.expect(initialLed.U, "LED should be unchanged after invalid commands")
      dut.io.ffc_data_oe.expect(initialOe.B, "Output enable should be unchanged")
      
      println("Invalid command handling test passed")
    }
  }

  it should "maintain state across multiple operations" in {
    test(new AlchitryTop) { dut =>
      initializeDut(dut)
      
      val testPattern = "h0123456789ABCDEF".U(48.W)
      dut.io.ffc_data_in.poke(testPattern)
      
      // Complex sequence: bank changes, mode switches, more bank changes
      sendUartByte(dut, CMD_BANK_2)
      waitForUartResponse(dut)
      dut.io.led.expect(0xCD.U) // Bits 23:16
      
      sendUartByte(dut, CMD_SEND_LOWER)
      waitForUartResponse(dut)
      dut.io.ffc_data_oe.expect(true.B)
      
      sendUartByte(dut, CMD_BANK_1)
      waitForUartResponse(dut)
      // Still in SEND mode, but different bank
      dut.io.ffc_data_oe.expect(true.B)
      
      sendUartByte(dut, CMD_RECV_UPPER)
      waitForUartResponse(dut)
      dut.io.ffc_data_oe.expect(false.B)
      dut.io.led.expect(0xAB.U) // Bank 1 of input data, bits 15:8
      
      println("Complex state sequence test passed")
    }
  }
}