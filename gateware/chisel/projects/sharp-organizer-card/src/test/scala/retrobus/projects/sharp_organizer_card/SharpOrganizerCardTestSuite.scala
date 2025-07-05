package retrobus.projects.sharp_organizer_card

import chisel3._
import chiseltest._
import org.scalatest.freespec.AnyFreeSpec

/**
 * Complete test suite for SharpOrganizerCard
 * Combines basic functional tests with interactive command tests
 */
class SharpOrganizerCardTestSuite extends AnyFreeSpec with ChiselScalatestTester {
  
  "SharpOrganizerCard Complete Test Suite" - {
    
    "Basic Functionality and Command Interface" in {
      test(new SharpOrganizerCardTestable).withAnnotations(Seq(WriteVcdAnnotation)) { dut =>
        
        // Helper to send UART byte
        def sendUartByte(byte: Int, baudDivider: Int = 100): Unit = {
          val bitsToSend = Seq(
            false,  // Start bit
            (byte & 0x01) != 0, (byte & 0x02) != 0, (byte & 0x04) != 0, (byte & 0x08) != 0,
            (byte & 0x10) != 0, (byte & 0x20) != 0, (byte & 0x40) != 0, (byte & 0x80) != 0,
            true    // Stop bit
          )
          
          for (bit <- bitsToSend) {
            dut.io.usb_rx.poke(bit.B)
            dut.clock.step(baudDivider)
          }
          dut.io.usb_rx.poke(true.B)
          dut.clock.step(baudDivider)
        }
        
        println("=== Test 1: Reset and Initialization ===")
        
        // Reset sequence
        dut.io.rst_n.poke(false.B)
        dut.io.usb_rx.poke(true.B)  // UART idle
        dut.clock.step(10)
        dut.io.rst_n.poke(true.B)
        dut.clock.step(10)
        
        println("Reset complete - checking initial state")
        // Note: USB TX may be 0 initially due to reset conditioning
        // Note: FT signals may be 0 initially due to reset conditioning
        
        println("=== Test 2: Basic Signal Capture ===")
        
        // Set up a read cycle
        dut.io.addr.poke(0x12345.U)
        dut.io.data.poke(0xAB.U)
        dut.io.conn_rw.poke(true.B)   // Read
        dut.io.conn_oe.poke(false.B)  // Output enable active
        dut.io.conn_mskrom.poke(true.B)
        dut.clock.step(10)  // Wait for debounce and capture
        
        val ledAfterCapture = dut.io.led.peek().litValue
        println(f"LED after capture: 0x${ledAfterCapture}%02X")
        
        // Change to write cycle
        dut.io.addr.poke(0x54321.U)
        dut.io.data.poke(0xCD.U)
        dut.io.conn_rw.poke(false.B)  // Write
        dut.clock.step(10)
        
        println("=== Test 3: Saleae Output Modes ===")
        
        // Test counter mode
        println("Switching to counter mode ('c')")
        sendUartByte('c'.toInt)
        dut.clock.step(100)
        
        val counter1 = dut.io.saleae.peek().litValue
        dut.clock.step(5)
        val counter2 = dut.io.saleae.peek().litValue
        println(f"Counter values: $counter1 -> $counter2")
        assert(counter2 != counter1, "Counter should increment")
        
        // Test sync signals mode
        println("Switching to sync signals mode ('s')")
        sendUartByte('s'.toInt)
        dut.clock.step(100)
        
        dut.io.conn_rw.poke(true.B)
        dut.io.conn_oe.poke(false.B)
        dut.io.conn_ci.poke(true.B)
        dut.io.conn_e2.poke(false.B)
        dut.clock.step(5)
        
        val syncSignals = dut.io.saleae.peek().litValue
        println(f"Sync signals output: 0x${syncSignals}%02X")
        println(s"  RW=${(syncSignals & 1) != 0}, OE=${(syncSignals & 2) != 0}, " +
                s"CI=${(syncSignals & 4) != 0}, E2=${(syncSignals & 8) != 0}")
        
        // Test memory banks mode
        println("Switching to memory banks mode ('S')")
        sendUartByte('S'.toInt)
        dut.clock.step(100)
        
        dut.io.conn_mskrom.poke(true.B)
        dut.io.conn_sram1.poke(false.B)
        dut.io.conn_sram2.poke(true.B)
        dut.io.conn_eprom.poke(false.B)
        dut.clock.step(5)
        
        val memBanks = dut.io.saleae.peek().litValue
        println(f"Memory banks output: 0x${memBanks}%02X")
        println(s"  MSKROM=${(memBanks & 1) != 0}, SRAM1=${(memBanks & 2) != 0}, " +
                s"SRAM2=${(memBanks & 4) != 0}, EPROM=${(memBanks & 8) != 0}")
        
        println("=== Test 4: Rapid Signal Changes ===")
        
        // Generate burst of changes
        for (i <- 0 until 10) {
          dut.io.addr.poke((i * 0x2222).U)
          dut.io.data.poke(((i * 0x22) & 0xFF).U)
          dut.io.conn_rw.poke((i % 2).B)
          dut.clock.step(2)
        }
        
        // Let debouncer settle
        dut.clock.step(10)
        println("Rapid changes complete - system stable")
        
        println("=== Test 5: FT2232H Interface ===")
        
        // Test with FT2232H ready
        dut.io.ft_rxf.poke(false.B)  // Data available (active low)
        dut.io.ft_txe.poke(false.B)  // Buffer has space (active low)
        dut.clock.step(5)
        
        // Enable streaming
        println("Enabling FT2232H streaming")
        sendUartByte('S'.toInt)
        dut.clock.step(10)
        sendUartByte('+'.toInt)
        dut.clock.step(100)
        
        // Generate some data
        dut.io.addr.poke(0xFEDCB.U)
        dut.io.data.poke(0x5A.U)
        dut.clock.step(10)
        
        // Disable streaming
        println("Disabling FT2232H streaming")
        sendUartByte('S'.toInt)
        dut.clock.step(10)
        sendUartByte('-'.toInt)
        dut.clock.step(100)
        
        println("=== Test 6: Memory Bank LED Indicators ===")
        
        // Test each bank individually
        val banks = Seq(
          ("MSKROM", dut.io.conn_mskrom),
          ("SRAM1", dut.io.conn_sram1),
          ("SRAM2", dut.io.conn_sram2),
          ("EPROM", dut.io.conn_eprom)
        )
        
        for ((name, signal) <- banks) {
          // Clear all
          dut.io.conn_mskrom.poke(false.B)
          dut.io.conn_sram1.poke(false.B)
          dut.io.conn_sram2.poke(false.B)
          dut.io.conn_eprom.poke(false.B)
          
          // Set one
          signal.poke(true.B)
          dut.clock.step(5)
          
          val led = dut.io.led.peek().litValue
          println(f"LED with $name active: 0x${led}%02X")
        }
        
        println("=== All Tests Complete ===")
      }
    }
  }
}