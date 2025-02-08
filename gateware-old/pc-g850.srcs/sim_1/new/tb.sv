`timescale 1ns / 1ps

module tb();
 
  logic clk;
  initial clk = '0;
  always begin
    clk = #5 ~clk; // change every 5ns
  end

//  localparam INPUT_DATA_WIDTH = 32;
//  logic [INPUT_DATA_WIDTH-1:0] data_in;

  logic [15:0] addr;
  logic [7:0] data;
  logic wr;
  logic rd;
  logic mreq;
  logic iorq;

  logic pll_locked;
  logic [3:0] sw;
  logic [3:0] btn;
  logic [3:0] led;
  logic [7:0] saleae;
  logic [7:0] saleae_gnd;

  top mytop (
    .clk_in(clk),
    .sw(sw),
    .btn(btn),
    .addr(addr),
    .data(data),
    .meta({4'd0, rd, wr, 3'd0, iorq, mreq, 1'd0}),

    .pll_locked(pll_locked),
    .led(led),
    .saleae(saleae),
    .saleae_gnd(saleae_gnd)
  );

//  test mytest(.in(clk), .out(led[0]));

  initial begin
    addr = '0;
    data = '0;
    rd = '1;
    wr = '1;
    mreq = '1;
    iorq = '1;
    
    sw = 15;
    btn = 0;

    wait(pll_locked == 1'b1);

    addr = 'hCAFE;

    // IMPORTANT: need to 2* all the clocks, since we're reducing the
    // frequency using PLL
    repeat (2*2) @(posedge clk);

    mreq = 0;
    repeat (2*2) @(posedge clk);
    rd = 0;
    data = 'hBE;
    repeat (2*2) @(posedge clk);
    rd = 1;
    mreq = 1;
    repeat (2*2) @(posedge clk);

    addr = 'hCAFE;
    mreq = 0;
    repeat (2*2) @(posedge clk);
    wr = 0;
    data = 'hBE;
    repeat (2*2) @(posedge clk);
    wr = 1;
    mreq = 1;
    repeat (2*2) @(posedge clk);

    // same data as first read
    addr = 'hCAFE;
    mreq = 0;
    repeat (2*2) @(posedge clk);
    rd = 0;
    data = 'hBE;
    repeat (2*2) @(posedge clk);
    rd = 1;
    mreq = 1;
    repeat (2*2) @(posedge clk);

    repeat (2*50) @(posedge clk);

// reset RAM
    btn = 1;
    repeat (2*2) @(posedge clk);
    btn = 0;
    repeat (2*2) @(posedge clk);

// repeat again
    mreq = 0;
    repeat (2*2) @(posedge clk);
    rd = 0;
    data = 'hBE;
    repeat (2*2) @(posedge clk);
    rd = 1;
    mreq = 1;
    repeat (2*2) @(posedge clk);

    addr = 'hCAFE;
    mreq = 0;
    repeat (2*2) @(posedge clk);
    wr = 0;
    data = 'hBE;
    repeat (2*2) @(posedge clk);
    wr = 1;
    mreq = 1;
    repeat (2*2) @(posedge clk);

    // same data as first read
    addr = 'hCAFE;
    mreq = 0;
    repeat (2*2) @(posedge clk);
    rd = 0;
    data = 'hBE;
    repeat (2*2) @(posedge clk);
    rd = 1;
    mreq = 1;
    repeat (2*2) @(posedge clk);

    repeat (2*50) @(posedge clk);

///////
    sw = 0;
    repeat (2*10) @(posedge clk);

    mreq = 0;
    repeat (2*2) @(posedge clk);
    rd = 0;
    data = 'hBE;
    repeat (2*2) @(posedge clk);
    rd = 1;
    mreq = 1;
    repeat (2*2) @(posedge clk);

    addr = 'hDEAD;
    mreq = 0;
    repeat (2*2) @(posedge clk);
    rd = 0;
    data = 'hAF;
    repeat (2*2) @(posedge clk);
    rd = 1;
    mreq = 1;
    repeat (2*2) @(posedge clk);

    // same data as first read
    addr = 'hCAFE;
    mreq = 0;
    repeat (2*2) @(posedge clk);
    rd = 0;
    data = 'hBE;
    repeat (2*2) @(posedge clk);
    rd = 1;
    mreq = 1;
    repeat (2*2) @(posedge clk);
 
    repeat (2*250) @(posedge clk);

//    data_in = 'hFEEDC0DE;
//    repeat (2*5) @(posedge clk);

//    repeat (2*10) @(posedge clk);

//$stop;

//    data_in = 'hAF;
//    repeat (3) @(posedge clk);

//    data_in = 'hFF;
//    repeat (30) @(posedge clk);

//    data_in = 'h00;
//    repeat (30) @(posedge clk);

//    $display("Waveform has been sampled and played back. You can view waves.");
    $stop;
  end
  
endmodule
