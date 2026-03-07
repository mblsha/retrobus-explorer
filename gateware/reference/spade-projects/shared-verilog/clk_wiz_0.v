
// Vivado clocking-wizard compatible wrapper.
// Synthesis uses MMCM primitives to generate 200 MHz and 400 MHz from 100 MHz.
// Simulation fallback uses passthrough clocks.
module clk_wiz_0 #(
    parameter BANDWIDTH = "OPTIMIZED",
    parameter STARTUP_WAIT = "FALSE"
) (
    output wire clk_out200,
    output wire clk_out400,
    input  wire clk_in100
);
`ifdef VERILATOR
  assign clk_out200 = clk_in100;
  assign clk_out400 = clk_in100;
`else
  wire clkfb_mmcm;
  wire clkfb_buf;
  wire clk_out200_mmcm;
  wire clk_out400_mmcm;

  BUFG clkfb_bufg (
      .I(clkfb_mmcm),
      .O(clkfb_buf)
  );

  BUFG clkout200_bufg (
      .I(clk_out200_mmcm),
      .O(clk_out200)
  );

  BUFG clkout400_bufg (
      .I(clk_out400_mmcm),
      .O(clk_out400)
  );

  MMCME2_BASE #(
      .BANDWIDTH(BANDWIDTH),
      .CLKIN1_PERIOD(10.000),
      .DIVCLK_DIVIDE(1),
      .CLKFBOUT_MULT_F(8.000),
      .CLKFBOUT_PHASE(0.000),
      .CLKOUT0_DIVIDE_F(4.000),
      .CLKOUT0_PHASE(0.000),
      .CLKOUT0_DUTY_CYCLE(0.500),
      .CLKOUT1_DIVIDE(2),
      .CLKOUT1_PHASE(0.000),
      .CLKOUT1_DUTY_CYCLE(0.500),
      .CLKOUT2_DIVIDE(1),
      .CLKOUT3_DIVIDE(1),
      .CLKOUT4_DIVIDE(1),
      .CLKOUT5_DIVIDE(1),
      .CLKOUT6_DIVIDE(1),
      .STARTUP_WAIT(STARTUP_WAIT)
  ) mmcm_inst (
      .CLKIN1(clk_in100),
      .CLKFBIN(clkfb_buf),
      .RST(1'b0),
      .PWRDWN(1'b0),
      .CLKFBOUT(clkfb_mmcm),
      .CLKOUT0(clk_out200_mmcm),
      .CLKOUT1(clk_out400_mmcm),
      .CLKOUT2(),
      .CLKOUT3(),
      .CLKOUT4(),
      .CLKOUT5(),
      .CLKOUT6(),
      .LOCKED()
  );
`endif
endmodule
