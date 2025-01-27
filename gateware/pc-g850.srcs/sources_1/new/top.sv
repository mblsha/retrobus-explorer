`timescale 1ns / 1ps

module top (
    input logic clk_in,
    input logic [3:0] sw,
    input logic [3:0] btn,
    input logic [15:0] addr,
    input logic [7:0] data,
    input logic [11:0] meta,

    `ifdef SIMULATION
    output logic pll_locked,
    `endif
    output logic [3:0] led,
    output logic [7:0] saleae,
    output logic [7:0] saleae_gnd
    );

  logic clk_write;
  logic clk_read;
  clk_wiz_0 myclk (
    .clk100(clk_in),
    .clk50(clk_write),
    .clk20(clk_read)
    `ifdef SIMULATION
    , .locked(pll_locked)
    `endif
  );

  logic [7:0] last_addr_hi100;
  logic [7:0] last_addr_lo100;
  logic [7:0] addr_hi_counter;
  logic [7:0] addr_lo_counter;
  initial begin
    last_addr_hi100 = '0;
    last_addr_lo100 = '0;
    addr_hi_counter = '0;
    addr_lo_counter = '0;
  end
  always @(posedge clk_in) begin
    if (last_addr_hi100 != addr[15:8]) begin
      last_addr_hi100 <= addr[15:8];
      addr_hi_counter <= addr_hi_counter + 1;
    end
    if (last_addr_lo100 != addr[7:0]) begin
      last_addr_lo100 <= addr[7:0];
      addr_lo_counter <= addr_lo_counter + 1;
    end
  end

  localparam INPUT_DATA_WIDTH = 32;
  logic [INPUT_DATA_WIDTH-1:0] data_in;
  logic [7:0] data_in_counter;

  logic [15:0] last_addr;
  logic [3:0] last_addr_meta;
  logic [7:0] last_data;

  logic [7:0] ram['hFFFF];
  logic ram_initialized['hFFFF];
  initial ram = '{default: '0};
  initial ram_initialized = '{default: '0};
  logic stream_only_changes;

  logic cur_m1;
  logic cur_mreq;
  logic cur_iorq;
  logic cur_iorst;
  logic cur_wait;
  logic cur_int1;
  logic cur_wr;
  logic cur_rd;

  logic cur_bnk0;
  logic cur_bnk1;
  logic cur_ceram2;
  logic cur_cerom2;

  logic last_m1;
  logic last_mreq;
  logic last_iorq;
  logic last_iorst;
  logic last_wait;
  logic last_int1;
  logic last_wr;
  logic last_rd;

  logic last_bnk0;
  logic last_bnk1;
  logic last_ceram2;
  logic last_cerom2;
  initial begin
    data_in_counter = '0;
    data_in = '0;

    last_addr = '0;
    last_addr_meta = '0;
    last_data = '0;

    last_m1 = '0;
    last_mreq = '0;
    last_iorq = '0;
    last_iorst = '0;
    last_wait = '0;
    last_int1 = '0;
    last_wr = '0;
    last_rd = '0;

    last_bnk0 = '0;
    last_bnk1 = '0;
    last_ceram2 = '0;
    last_cerom2 = '0;
  end
  always_comb begin
    stream_only_changes = sw == 15;
    led = data_in_counter;

    `ifdef SIMULATION
    if (pll_locked) begin
    `endif
    
    cur_m1    = meta[0];
    cur_mreq  = meta[1];
    cur_iorq  = meta[2];
    cur_iorst = meta[3];
    cur_wait  = meta[4];
    cur_int1  = meta[5];
    cur_wr    = meta[6];
    cur_rd    = meta[7];

    cur_bnk0 = meta[8];
    cur_bnk1 = meta[9];
    cur_ceram2 = meta[10];
    cur_cerom2 = meta[11];

    `ifdef SIMULATION
    end
    `endif
  end
  always @(posedge clk_write) begin
    // if (btn) begin
    //   ram_initialized <= '{default: 0};
    // end

    // FIXME: wait for next cycle to capture last_addr?
    if (!cur_mreq && last_mreq) begin
      last_addr <= addr;
      last_addr_meta <= {cur_bnk0, cur_bnk1, cur_ceram2, cur_cerom2};
    end else if (!cur_iorq && last_iorq) begin
      last_addr <= {8'd0, addr[7:0]};
      last_addr_meta <= {cur_bnk0, cur_bnk1, cur_ceram2, cur_cerom2};
    end

    if (!last_mreq && cur_rd && !last_rd) begin
      // 1: Read
      if (stream_only_changes) begin
        if (!ram_initialized[last_addr] || ram[last_addr] != data) begin
          ram[last_addr] <= data;
          ram_initialized[last_addr] = 1;
          data_in <= {last_addr_meta, 4'd1, data, last_addr};
        end
      end else begin
        data_in <= {last_addr_meta, 4'd1, data, last_addr};
      end
    end else if (!last_mreq && cur_wr && !last_wr) begin
      // 2: Write
      if (stream_only_changes) begin
        if (!ram_initialized[last_addr] || ram[last_addr] != data) begin
          ram[last_addr] <= last_data;
          ram_initialized[last_addr] = 1;
          data_in <= {last_addr_meta, 4'd2, last_data, last_addr};
        end
      end else begin
        data_in <= {last_addr_meta, 4'd2, last_data, last_addr};
      end
    end else if (!last_iorq && cur_rd && !last_rd) begin
      // 3: IO Read
      if (!stream_only_changes) begin
        data_in <= {last_addr_meta, 4'd3, data, last_addr};
      end
    end else if (!last_iorq && cur_wr && !last_wr) begin
      // 4: IO Write
      if (!stream_only_changes) begin
        data_in <= {last_addr_meta, 4'd4, last_data, last_addr};
      end
    end

    // last_addr <= addr;
    last_data <= data;

    last_m1 <= cur_m1;
    last_mreq <= cur_mreq;
    last_iorq <= cur_iorq;
    last_iorst <= cur_iorst;
    last_wait <= cur_wait;
    last_int1 <= cur_int1;
    last_wr <= cur_wr;
    last_rd <= cur_rd;

    last_bnk0 <= cur_bnk0;
    last_bnk1 <= cur_bnk1;
    last_ceram2 <= cur_ceram2;
    last_cerom2 <= cur_cerom2;
  end


  // FIFO interface signals
  logic fifo_wr_en;
  logic fifo_rd_en;
  logic [INPUT_DATA_WIDTH-1:0] fifo_din;
  logic [INPUT_DATA_WIDTH-1:0] fifo_dout;
  logic fifo_full;
  logic fifo_empty;
  fifo_generator_32 your_fifo (
      .wr_clk(clk_write),
      .rd_clk(clk_read),
      .din(fifo_din),
      .wr_en(fifo_wr_en),
      .rd_en(fifo_rd_en),
      .dout(fifo_dout),
      .full(fifo_full),
      .empty(fifo_empty)
  );
  
  // put input into FIFO
  initial begin
    fifo_wr_en = '0;
    fifo_rd_en = '0;
    fifo_din = '0;
    fifo_dout = '0;
    fifo_full = '0;
    fifo_empty = '0;
  end
  always @(posedge clk_write) begin
    fifo_wr_en <= '0;
    if (data_in != fifo_din) begin
      fifo_din <= data_in;
      fifo_wr_en <= '1;
      data_in_counter <= data_in_counter + 1;
    end
  end

  // output to Saleae
  localparam OUTPUT_DATA_WIDTH = 7;
  logic [$clog2(INPUT_DATA_WIDTH+2)-1:0] out_buf_counter;
  logic out_en;
  // external
  logic out_clk;
  logic [OUTPUT_DATA_WIDTH-1:0] out_wires;
  initial begin
    out_buf_counter = INPUT_DATA_WIDTH;
    out_en = '0;

    out_clk = '0;
    out_wires = '0;
  end
  always @(posedge clk_read) begin
    fifo_rd_en <= '0;
    out_en <= '0;
    out_wires <= '0;
    if (out_buf_counter == INPUT_DATA_WIDTH) begin
      if (!fifo_empty) begin
        fifo_rd_en <= '1;
        out_buf_counter <= out_buf_counter + 1;
      end      
    end else if (out_buf_counter > INPUT_DATA_WIDTH) begin
      // one-cycle pipeline to read fifo_dout
      out_buf_counter <= '0;
    end else begin
      out_wires <= fifo_dout[out_buf_counter +: OUTPUT_DATA_WIDTH];
      out_en <= '1;

      out_buf_counter <= out_buf_counter + OUTPUT_DATA_WIDTH > INPUT_DATA_WIDTH ?
        INPUT_DATA_WIDTH :
        out_buf_counter + OUTPUT_DATA_WIDTH;
    end
  end
  assign out_clk = clk_read & out_en;

  always_comb begin
    if (sw == 1) begin
      saleae = data_in_counter;
    end else if (sw == 2) begin
      saleae = addr[7:0];
    end else if (sw == 3) begin
      saleae = addr[15:7];
    end else if (sw == 4) begin
      saleae = data;
    end else if (sw == 5) begin
      saleae = meta;
    end else if (stream_only_changes) begin
      // sw == 15
      saleae = {out_wires, out_clk};
    end else begin
      saleae = {out_wires, out_clk};
    end
    saleae_gnd = '0;
  end
endmodule

