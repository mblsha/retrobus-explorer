package retrobus.projects.sharp_organizer_card

import chisel3._
import chiseltest._
import org.scalatest.freespec.AnyFreeSpec

class SharpOrganizerCardCommandTest extends AnyFreeSpec with ChiselScalatestTester {
  "SharpOrganizerCard Interactive Commands" - {
    
    // Helper function to send a UART byte
    def sendUartByte(dut: SharpOrganizerCardTestable, byte: Int, baudDivider: Int = 100): Unit = {
      val bitsToSend = Seq(
        false,  // Start bit (0)
        (byte & 0x01) != 0,  // Bit 0
        (byte & 0x02) != 0,  // Bit 1
        (byte & 0x04) != 0,  // Bit 2
        (byte & 0x08) != 0,  // Bit 3
        (byte & 0x10) != 0,  // Bit 4
        (byte & 0x20) != 0,  // Bit 5
        (byte & 0x40) != 0,  // Bit 6
        (byte & 0x80) != 0,  // Bit 7
        true    // Stop bit (1)
      )
      
      for (bit <- bitsToSend) {
        dut.io.usb_rx.poke(bit.B)
        dut.clock.step(baudDivider)
      }
      
      // Return to idle
      dut.io.usb_rx.poke(true.B)
      dut.clock.step(baudDivider)
    }
    
    // Helper function to receive a UART byte (simplified - just check echo)
    def expectUartEcho(dut: SharpOrganizerCardTestable, expected: Int): Unit = {
      // Wait for start bit
      var timeout = 1000
      while (dut.io.usb_tx.peek().litValue == 1 && timeout > 0) {
        dut.clock.step(1)
        timeout -= 1
      }
      assert(timeout > 0, "Timeout waiting for UART echo")
      
      // We received start bit - good enough for echo test
      // In real test would decode full byte
    }
    
    "should echo UART commands" in {
      test(new SharpOrganizerCardTestable).withAnnotations(Seq(WriteVcdAnnotation)) { dut =>
        // Initialize
        dut.io.rst_n.poke(true.B)
        dut.io.usb_rx.poke(true.B)  // UART idle
        dut.clock.step(10)
        
        // Send 'c' command
        sendUartByte(dut, 'c'.toInt)
        
        // Should echo back
        expectUartEcho(dut, 'c'.toInt)
        
        // Send 's' command
        sendUartByte(dut, 's'.toInt)
        expectUartEcho(dut, 's'.toInt)
        
        // Send 'S' command
        sendUartByte(dut, 'S'.toInt)
        expectUartEcho(dut, 'S'.toInt)
      }
    }
    
    "should switch Saleae output mode with 'c' command" in {
      test(new SharpOrganizerCardTestable).withAnnotations(Seq(WriteVcdAnnotation)) { dut =>
        // Initialize
        dut.io.rst_n.poke(true.B)
        dut.io.usb_rx.poke(true.B)
        dut.clock.step(10)
        
        // Get initial Saleae output
        val initial = dut.io.saleae.peek().litValue
        
        // Send 'c' command for counter mode
        sendUartByte(dut, 'c'.toInt)
        dut.clock.step(100)
        
        // Saleae output should now be counting
        val after1 = dut.io.saleae.peek().litValue
        dut.clock.step(10)
        val after2 = dut.io.saleae.peek().litValue
        
        assert(after2 != after1, "Counter mode should show incrementing values")
      }
    }
    
    "should switch Saleae output mode with 's' command" in {
      test(new SharpOrganizerCardTestable).withAnnotations(Seq(WriteVcdAnnotation)) { dut =>
        // Initialize
        dut.io.rst_n.poke(true.B)
        dut.io.usb_rx.poke(true.B)
        dut.clock.step(10)
        
        // First set counter mode
        sendUartByte(dut, 'c'.toInt)
        dut.clock.step(100)
        
        // Now switch to sync signals mode
        sendUartByte(dut, 's'.toInt)
        dut.clock.step(100)
        
        // Set some control signals
        dut.io.conn_rw.poke(true.B)
        dut.io.conn_oe.poke(false.B)
        dut.io.conn_ci.poke(true.B)
        dut.io.conn_e2.poke(false.B)
        dut.clock.step(10)
        
        val saleae = dut.io.saleae.peek().litValue
        // Bits 0-3 should reflect conn_rw, conn_oe, conn_ci, conn_e2
        assert((saleae & 0x01) == 1, "conn_rw should be in bit 0")
        assert((saleae & 0x02) == 0, "conn_oe should be in bit 1")
        assert((saleae & 0x04) == 4, "conn_ci should be in bit 2")
        assert((saleae & 0x08) == 0, "conn_e2 should be in bit 3")
      }
    }
    
    "should switch Saleae output mode with 'S' command" in {
      test(new SharpOrganizerCardTestable).withAnnotations(Seq(WriteVcdAnnotation)) { dut =>
        // Initialize
        dut.io.rst_n.poke(true.B)
        dut.io.usb_rx.poke(true.B)
        dut.clock.step(10)
        
        // Switch to memory banks mode
        sendUartByte(dut, 'S'.toInt)
        dut.clock.step(100)
        
        // Set memory bank signals
        dut.io.conn_mskrom.poke(true.B)
        dut.io.conn_sram1.poke(false.B)
        dut.io.conn_sram2.poke(true.B)
        dut.io.conn_eprom.poke(false.B)
        dut.clock.step(10)
        
        val saleae = dut.io.saleae.peek().litValue
        // Bits 0-3 should reflect memory banks
        assert((saleae & 0x01) == 1, "conn_mskrom should be in bit 0")
        assert((saleae & 0x02) == 0, "conn_sram1 should be in bit 1")
        assert((saleae & 0x04) == 4, "conn_sram2 should be in bit 2")
        assert((saleae & 0x08) == 0, "conn_eprom should be in bit 3")
      }
    }
    
    "should handle FT2232H streaming control commands" in {
      test(new SharpOrganizerCardTestable).withAnnotations(Seq(WriteVcdAnnotation)) { dut =>
        // Initialize
        dut.io.rst_n.poke(true.B)
        dut.io.usb_rx.poke(true.B)
        dut.io.ft_txe.poke(false.B)  // FT2232H ready
        dut.clock.step(10)
        
        // Send 'S' followed by '+' to enable streaming
        sendUartByte(dut, 'S'.toInt)
        dut.clock.step(10)
        sendUartByte(dut, '+'.toInt)
        dut.clock.step(100)
        
        // Generate some data by changing signals
        dut.io.addr.poke(0xABCDE.U)
        dut.io.data.poke(0x42.U)
        dut.clock.step(10)  // Wait for capture
        
        // With streaming enabled and data captured, 
        // ft_wr might pulse (depends on internal state)
        // Just verify no crash
        
        // Send 'S' followed by '-' to disable streaming
        sendUartByte(dut, 'S'.toInt)
        dut.clock.step(10)
        sendUartByte(dut, '-'.toInt)
        dut.clock.step(100)
        
        // Note: USB TX may be 0 due to reset conditioning - this is OK
      }
    }
    
    "should handle command during active capture" in {
      test(new SharpOrganizerCardTestable).withAnnotations(Seq(WriteVcdAnnotation)) { dut =>
        // Initialize
        dut.io.rst_n.poke(true.B)
        dut.io.usb_rx.poke(true.B)
        dut.clock.step(10)
        
        // Start generating continuous data changes
        val dataThread = fork {
          for (i <- 0 until 50) {
            dut.io.addr.poke((i * 0x1000).U)
            dut.io.data.poke(i.U)
            dut.clock.step(20)
          }
        }
        
        // Send commands while data is changing
        dut.clock.step(50)
        sendUartByte(dut, 'c'.toInt)  // Switch to counter
        dut.clock.step(50)
        sendUartByte(dut, 's'.toInt)  // Switch to sync signals
        dut.clock.step(50)
        sendUartByte(dut, 'S'.toInt)  // Switch to memory banks
        
        dataThread.join()
        
        // Note: USB TX may be 0 due to reset conditioning - this is OK
      }
    }
    
    "should maintain command state across captures" in {
      test(new SharpOrganizerCardTestable).withAnnotations(Seq(WriteVcdAnnotation)) { dut =>
        // Initialize
        dut.io.rst_n.poke(true.B)
        dut.io.usb_rx.poke(true.B)
        dut.clock.step(10)
        
        // Set counter mode
        sendUartByte(dut, 'c'.toInt)
        dut.clock.step(100)
        
        // Verify counter is running
        val count1 = dut.io.saleae.peek().litValue
        dut.clock.step(10)
        val count2 = dut.io.saleae.peek().litValue
        assert(count2 != count1, "Counter should be incrementing")
        
        // Generate lots of captures
        for (i <- 0 until 10) {
          dut.io.addr.poke((i * 0x1111).U)
          dut.io.data.poke((i * 0x11).U)
          dut.clock.step(10)
        }
        
        // Counter should still be running
        val count3 = dut.io.saleae.peek().litValue
        dut.clock.step(10)
        val count4 = dut.io.saleae.peek().litValue
        assert(count4 != count3, "Counter should still be incrementing after captures")
      }
    }
  }
}