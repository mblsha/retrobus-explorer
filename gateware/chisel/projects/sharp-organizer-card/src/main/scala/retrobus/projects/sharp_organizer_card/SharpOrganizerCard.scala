package retrobus.projects.sharp_organizer_card

import chisel3._
import chisel3.util._
import retrobus.library.reset.ResetConditioner
import retrobus.library.uart._
import retrobus.library.common._
import retrobus.library.ft.FT2232HTestable

/**
 * Sharp Organizer Card bus monitor
 * Captures and streams address, data, and control signals
 * from a Sharp Organizer card interface
 */
class SharpOrganizerCard extends Module {
  val io = IO(new Bundle {
    // System
    val clk = Input(Clock())
    val rst_n = Input(Bool())
    val led = Output(UInt(8.W))
    
    // USB UART
    val usb_rx = Input(Bool())
    val usb_tx = Output(Bool())
    
    // FT2232H interface (simplified for now)
    val ft_clk = Input(Clock())
    val ft_rxf = Input(Bool())
    val ft_txe = Input(Bool())
    val ft_data_in = Input(UInt(16.W))
    val ft_data_out = Output(UInt(16.W))
    val ft_data_oe = Output(Bool())
    val ft_be_out = Output(UInt(2.W))
    val ft_be_oe = Output(Bool())
    val ft_rd = Output(Bool())
    val ft_wr = Output(Bool())
    val ft_oe = Output(Bool())
    
    // Saleae debug outputs
    val saleae = Output(UInt(8.W))
    
    // Sharp Organizer interface
    val conn_rw = Input(Bool())
    val conn_oe = Input(Bool())
    val conn_ci = Input(Bool())
    val conn_e2 = Input(Bool())
    val conn_mskrom = Input(Bool())
    val conn_sram1 = Input(Bool())
    val conn_sram2 = Input(Bool())
    val conn_eprom = Input(Bool())
    val conn_stnby = Input(Bool())
    val conn_vbatt = Input(Bool())
    val conn_vpp = Input(Bool())
    val addr = Input(UInt(20.W))
    val data = Input(UInt(8.W))
  })

  // Use explicit clock
  withClock(io.clk) {
    // Reset conditioning
    val resetCond = Module(new ResetConditioner)
    resetCond.io.in := !io.rst_n
    val rst = resetCond.io.out
    
    withReset(rst.asAsyncReset) {
      // Synchronize all input signals
      val connRwSync = ShiftRegister(io.conn_rw, 2)
      val connOeSync = ShiftRegister(io.conn_oe, 2)
      val connCiSync = ShiftRegister(io.conn_ci, 2)
      val connE2Sync = ShiftRegister(io.conn_e2, 2)
      val connMskromSync = ShiftRegister(io.conn_mskrom, 2)
      val connSram1Sync = ShiftRegister(io.conn_sram1, 2)
      val connSram2Sync = ShiftRegister(io.conn_sram2, 2)
      val connEpromSync = ShiftRegister(io.conn_eprom, 2)
      val connStnbySync = ShiftRegister(io.conn_stnby, 2)
      val connVbattSync = ShiftRegister(io.conn_vbatt, 2)
      val connVppSync = ShiftRegister(io.conn_vpp, 2)
      val addrSync = ShiftRegister(io.addr, 2)
      val dataSync = ShiftRegister(io.data, 2)
      
      // Edge detectors for control signals
      val rwEdge = Module(new EdgeDetector)
      rwEdge.io.in := connRwSync
      
      val oeEdge = Module(new EdgeDetector)
      oeEdge.io.in := connOeSync
      
      val ciEdge = Module(new EdgeDetector)
      ciEdge.io.in := connCiSync
      
      val e2Edge = Module(new EdgeDetector)
      e2Edge.io.in := connE2Sync
      
      // Previous values for change detection
      val addrPrev = RegNext(addrSync)
      val dataPrev = RegNext(dataSync)
      val connRwPrev = RegNext(connRwSync)
      val connOePrev = RegNext(connOeSync)
      val connCiPrev = RegNext(connCiSync)
      val connE2Prev = RegNext(connE2Sync)
      val connMskromPrev = RegNext(connMskromSync)
      val connSram1Prev = RegNext(connSram1Sync)
      val connSram2Prev = RegNext(connSram2Sync)
      val connEpromPrev = RegNext(connEpromSync)
      
      // Change detection
      val addrChanged = addrSync =/= addrPrev
      val dataChanged = dataSync =/= dataPrev
      val connRwChanged = connRwSync =/= connRwPrev
      val connOeChanged = connOeSync =/= connOePrev
      val connCiChanged = connCiSync =/= connCiPrev
      val connE2Changed = connE2Sync =/= connE2Prev
      val connMskromChanged = connMskromSync =/= connMskromPrev
      val connSram1Changed = connSram1Sync =/= connSram1Prev
      val connSram2Changed = connSram2Sync =/= connSram2Prev
      val connEpromChanged = connEpromSync =/= connEpromPrev
      
      // Any change occurred
      val anyChange = addrChanged || dataChanged || connRwChanged || 
                     connOeChanged || connCiChanged || connE2Changed ||
                     connMskromChanged || connSram1Changed || 
                     connSram2Changed || connEpromChanged
      
      // Debounce counter
      val ctr = RegInit(0.U(3.W))
      when(anyChange) {
        ctr := 0.U
      }.elsewhen(ctr =/= 5.U) {
        ctr := ctr + 1.U
      }
      
      // Capture stable values
      val capture = ctr === 5.U
      
      // USB UART (1Mbps on 100MHz clock)
      val uartRx = Module(new UartRx(clkFreq = 100_000_000, baud = 1_000_000))
      uartRx.io.rx := io.usb_rx
      
      val uartTx = Module(new UartTx(clkFreq = 100_000_000, baud = 1_000_000))
      io.usb_tx := uartTx.io.tx
      uartTx.io.block := false.B
      
      // High-speed UART transmitters (100Mbps on 400MHz clock)
      // For now, use 100MHz clock with 10Mbps
      val txAddr = Module(new MyUartTx(clkFreq = 100_000_000, baud = 10_000_000, dataWidth = 20))
      val txData = Module(new MyUartTx(clkFreq = 100_000_000, baud = 10_000_000, dataWidth = 8))
      val txMisc = Module(new MyUartTx(clkFreq = 100_000_000, baud = 10_000_000, dataWidth = 11))
      
      // Async FIFOs for data capture
      val addrFifo = Module(new AsyncFifo(width = 20, depth = 256))
      val dataFifo = Module(new AsyncFifo(width = 8, depth = 256))
      val miscFifo = Module(new AsyncFifo(width = 11, depth = 256))
      
      // Pack misc signals
      val miscPacked = Cat(
        connEpromSync,    // bit 10
        connSram2Sync,    // bit 9
        connSram1Sync,    // bit 8
        connMskromSync,   // bit 7
        connVppSync,      // bit 6
        connVbattSync,    // bit 5
        connStnbySync,    // bit 4
        connE2Sync,       // bit 3
        connCiSync,       // bit 2
        connOeSync,       // bit 1
        connRwSync        // bit 0
      )
      
      // Write to FIFOs on capture
      addrFifo.io.din := addrSync
      addrFifo.io.wr_en := capture
      
      dataFifo.io.din := dataSync
      dataFifo.io.wr_en := capture
      
      miscFifo.io.din := miscPacked
      miscFifo.io.wr_en := capture
      
      // Connect FIFOs to UART transmitters
      txAddr.io.data := addrFifo.io.dout
      txAddr.io.newData := !addrFifo.io.empty && !txAddr.io.busy
      txAddr.io.block := false.B
      addrFifo.io.rd_en := !addrFifo.io.empty && !txAddr.io.busy
      
      txData.io.data := dataFifo.io.dout
      txData.io.newData := !dataFifo.io.empty && !txData.io.busy
      txData.io.block := false.B
      dataFifo.io.rd_en := !dataFifo.io.empty && !txData.io.busy
      
      txMisc.io.data := miscFifo.io.dout
      txMisc.io.newData := !miscFifo.io.empty && !txMisc.io.busy
      txMisc.io.block := false.B
      miscFifo.io.rd_en := !miscFifo.io.empty && !txMisc.io.busy
      
      // FT2232H interface
      val ft = Module(new FT2232HTestable)
      ft.io.ftRxf := io.ft_rxf
      ft.io.ftTxe := io.ft_txe
      ft.io.ftDataIn := io.ft_data_in
      io.ft_data_out := ft.io.ftDataOut
      io.ft_data_oe := ft.io.ftDataOutEn
      io.ft_be_out := "b11".U  // Both bytes enabled
      io.ft_be_oe := ft.io.ftDataOutEn
      io.ft_rd := ft.io.ftRd
      io.ft_wr := ft.io.ftWr
      io.ft_oe := ft.io.ftOe
      
      // FT2232H streaming control
      val ftStreamEnable = RegInit(false.B)
      when(uartRx.io.newData) {
        val cmd = uartRx.io.data
        when(cmd === 'S'.U && uartRx.io.newData) {
          when(RegNext(uartRx.io.data) === '+'.U) {
            ftStreamEnable := true.B
          }.elsewhen(RegNext(uartRx.io.data) === '-'.U) {
            ftStreamEnable := false.B
          }
        }
      }
      
      // Pack data for FT2232H streaming
      val ftData32 = Cat(0.U(1.W), miscPacked, dataSync, addrSync(11, 0))
      ft.io.txData := ftData32(15, 0)  // Lower 16 bits
      ft.io.txWrite := ftStreamEnable && capture
      
      // Saleae output modes
      object SaleaeMode extends ChiselEnum {
        val SYNC_SIGNALS, COUNTER = Value
      }
      object SyncSubMode extends ChiselEnum {
        val STANDARD_SIGNALS, MEMORY_BANKS = Value
      }
      
      val saleaeMode = RegInit(SaleaeMode.SYNC_SIGNALS)
      val syncSubMode = RegInit(SyncSubMode.STANDARD_SIGNALS)
      val counter = RegInit(0.U(8.W))
      counter := counter + 1.U
      
      // Default outputs
      io.saleae := 0.U
      uartTx.io.data := 0.U
      uartTx.io.newData := false.B
      
      // UART command processing
      when(uartRx.io.newData) {
        uartTx.io.data := uartRx.io.data
        uartTx.io.newData := true.B
        
        switch(uartRx.io.data) {
          is('c'.U) { saleaeMode := SaleaeMode.COUNTER }
          is('s'.U) { 
            saleaeMode := SaleaeMode.SYNC_SIGNALS
            syncSubMode := SyncSubMode.STANDARD_SIGNALS
          }
          is('S'.U) {
            saleaeMode := SaleaeMode.SYNC_SIGNALS
            syncSubMode := SyncSubMode.MEMORY_BANKS
          }
        }
      }.otherwise {
        uartTx.io.newData := false.B
        uartTx.io.data := 0.U
      }
      
      // Saleae output selection
      switch(saleaeMode) {
        is(SaleaeMode.COUNTER) {
          io.saleae := counter
        }
        is(SaleaeMode.SYNC_SIGNALS) {
          switch(syncSubMode) {
            is(SyncSubMode.STANDARD_SIGNALS) {
              io.saleae := Cat(
                capture,
                txMisc.io.tx,
                txData.io.tx,
                txAddr.io.tx,
                connE2Sync,
                connCiSync,
                connOeSync,
                connRwSync
              )
            }
            is(SyncSubMode.MEMORY_BANKS) {
              io.saleae := Cat(
                capture,
                txMisc.io.tx,
                txData.io.tx,
                txAddr.io.tx,
                connEpromSync,
                connSram2Sync,
                connSram1Sync,
                connMskromSync
              )
            }
          }
        }
      }
      
      // LED output - show activity
      io.led := Cat(
        !addrFifo.io.empty,
        !dataFifo.io.empty,
        !miscFifo.io.empty,
        capture,
        connEpromSync,
        connSram2Sync,
        connSram1Sync,
        connMskromSync
      )
    }
  }
}