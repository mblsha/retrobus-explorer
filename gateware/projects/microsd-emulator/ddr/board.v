module board(
output wire   [13:0] ddram_a,
output wire    [2:0] ddram_ba,
output wire          ddram_cas_n,
output wire          ddram_cke,
output wire          ddram_clk_n,
output wire          ddram_clk_p,
output wire          ddram_cs_n,
output wire    [1:0] ddram_dm,
inout  wire   [15:0] ddram_dq,
inout  wire    [1:0] ddram_dqs_n,
inout  wire    [1:0] ddram_dqs_p,
output wire          ddram_odt,
output wire          ddram_ras_n,
output wire          ddram_reset_n,
output wire          ddram_we_n,
input wire clk, reset_button, usb_rx,
output wire usb_tx,
output wire [2:0] status,
inout wire [7:0] pmod
);

wire dclk,drst;
wire bios_tx,sd_tx;
wire [6:0] sd_status_selector;
// Both UARTs idle high. Read BIOS boot at 115200; use the Spade loader at
// 1 Mbaud after boot output has stopped. Do not send loader packets during boot.
assign usb_tx = bios_tx & sd_tx;
wire fcv,fcr,fcw,fwv,fwr,frv,frr;
wire [23:0] fa;
wire [127:0] fwdata,frdata;
wire [15:0] fwmask;
wire co,ce,armed;
wire [3:0] dout,doe;
ddr_uart_100 sd(
.writable(1'b1),.dat_in({pmod[1],pmod[0],pmod[7],pmod[3]}),
.clk(fclk),.rst(frst),.initialized(fast_passed[1]),.diagnostic_status(fast_status),.status_selector(sd_status_selector),.usb_rx(usb_rx),.usb_tx(sd_tx),
.ddr_cmd_valid(fcv),.ddr_cmd_ready(fcr),.ddr_cmd_address(fa),.ddr_cmd_write(fcw),
.ddr_wdata_valid(fwv),.ddr_wdata_ready(fwr),.ddr_wdata(fwdata),.ddr_wdata_mask(fwmask),
.ddr_rdata_valid(frv),.ddr_rdata_ready(frr),.ddr_rdata(frdata),
.sd_clk(pmod[6]),.cmd_in(pmod[2]),.cmd_out(co),.cmd_oe(ce),
.dat_out(dout),.dat_oe(doe),.armed_status(armed));
assign pmod[2] = ce ? co : 1'bz;
assign pmod[3] = doe[0] ? dout[0] : 1'bz;
assign pmod[7] = doe[1] ? dout[1] : 1'bz;
assign pmod[0] = doe[2] ? dout[2] : 1'bz;
assign pmod[1] = doe[3] ? dout[3] : 1'bz;

wire pcv,pcr,pcw,pwv,pwr,prv,prr;
wire [23:0] pa;
wire [127:0] pwdata,prdata;
wire [15:0] pwmask;
wire bist_busy,bist_passed,bist_failed;
wire [23:0] bist_progress;
wire [4:0] bist_diagnostic;
wire [127:0] bist_expected,bist_actual;
wire [296:0] bist_detail = {9'd0,bist_expected,bist_actual,8'd0,bist_progress};
reg [26:0] bist_status_mux;
wire [15:0] sd_peak_edges;
wire [31:0] sd_total_edges;
wire [23:0] sd_minimum_period,sd_latest_period;
sd_clock_meter clock_measurement(.clk(dclk),.rst(drst),.sd_clk(pmod[6]),
.window_cycles(17'd80000),.peak_edges(sd_peak_edges),.minimum_period(sd_minimum_period),.latest_period(sd_latest_period),.total_edges(sd_total_edges));
qualified_ddr qualification(
.clk(dclk),.rst(drst),.start(status[0] && !status[1]),
.word_count(25'd16777216),.timeout_cycles(20'd1000000),
.cmd_valid(pcv),.cmd_ready(pcr),.cmd_address(pa),.cmd_write(pcw),
.wdata_valid(pwv),.wdata_ready(pwr),.wdata(pwdata),.wdata_mask(pwmask),
.rdata_valid(prv),.rdata_ready(prr),.rdata(prdata),
.client_cmd_valid(scv),.client_cmd_ready(scr),.client_cmd_address(sa),.client_cmd_write(scw),
.client_wdata_valid(swv),.client_wdata_ready(swr),.client_wdata(swdata),.client_wdata_mask(swmask),
.client_rdata_valid(srv),.client_rdata_ready(srr),.client_rdata(srdata),
.busy(bist_busy),.passed(bist_passed),.failed(bist_failed),.progress(bist_progress),.diagnostic(bist_diagnostic),.expected_word(bist_expected),.actual_word(bist_actual));

always @* begin
case (slow_selector)
0: bist_status_mux = {bist_diagnostic,bist_progress[23:5],bist_failed,bist_passed,bist_busy};
1: bist_status_mux = bist_detail[0 +: 27];
2: bist_status_mux = bist_detail[27 +: 27];
3: bist_status_mux = bist_detail[54 +: 27];
4: bist_status_mux = bist_detail[81 +: 27];
5: bist_status_mux = bist_detail[108 +: 27];
6: bist_status_mux = bist_detail[135 +: 27];
7: bist_status_mux = bist_detail[162 +: 27];
8: bist_status_mux = bist_detail[189 +: 27];
9: bist_status_mux = bist_detail[216 +: 27];
10: bist_status_mux = bist_detail[243 +: 27];
11: bist_status_mux = bist_detail[270 +: 27];
120: bist_status_mux = {11'd0,sd_peak_edges};
121: bist_status_mux = {3'd0,sd_minimum_period};
122: bist_status_mux = {3'd0,sd_latest_period};
123: bist_status_mux = sd_total_edges[26:0];
124: bist_status_mux = {22'd0,sd_total_edges[31:27]};
127: bist_status_mux = 27'h534244;
default: bist_status_mux = 0;
endcase
end

wire mcv,mcr,mcw,mwv,mwr,mrv,mrr;
wire [23:0] ma;
wire [127:0] mwdata,mrdata;
wire [15:0] mwmask;
native_stage native_registers(
.clk(dclk),.rst(drst),
.s_cmd_valid(pcv),.s_cmd_ready(pcr),.s_cmd_address(pa),.s_cmd_write(pcw),
.s_wdata_valid(pwv),.s_wdata_ready(pwr),.s_wdata(pwdata),.s_wmask(pwmask),
.s_rdata_valid(prv),.s_rdata_ready(prr),.s_rdata(prdata),
.m_cmd_valid(mcv),.m_cmd_ready(mcr),.m_cmd_address(ma),.m_cmd_write(mcw),
.m_wdata_valid(mwv),.m_wdata_ready(mwr),.m_wdata(mwdata),.m_wmask(mwmask),
.m_rdata_valid(mrv),.m_rdata_ready(mrr),.m_rdata(mrdata));

wire fclk;
reg [7:0] fast_reset = 8'hff;
always @(posedge fclk or posedge drst)
    if (drst) fast_reset <= 8'hff;
    else fast_reset <= {fast_reset[6:0],1'b0};
wire frst = fast_reset[7];
(* ASYNC_REG = "TRUE" *) reg [1:0] fast_passed;
(* ASYNC_REG = "TRUE" *) reg [26:0] fast_status_meta,fast_status;
(* ASYNC_REG = "TRUE" *) reg [6:0] slow_selector_meta,slow_selector;
always @(posedge fclk) begin
    if (frst) begin fast_passed <= 0; fast_status_meta <= 0; fast_status <= 0; end
    else begin
        fast_passed <= {fast_passed[0],bist_passed};
        fast_status_meta <= bist_status_mux;
        fast_status <= fast_status_meta;
    end
end
// Selector remains stable throughout the remainder of the UART packet.
// Diagnostic values settle before the acknowledgment samples them.
always @(posedge dclk) begin
    if (drst) begin slow_selector_meta <= 0; slow_selector <= 0; end
    else begin slow_selector_meta <= sd_status_selector; slow_selector <= slow_selector_meta; end
end
wire scv,scr,scw,swv,swr,srv,srr;
wire [23:0] sa;
wire [127:0] swdata,srdata;
wire [15:0] swmask;
native_cdc sd_memory_crossing(
.s_clk(fclk),.s_rst(frst),.m_clk(dclk),.m_rst(drst),
.s_cmd_valid(fcv),.s_cmd_ready(fcr),.s_cmd_address(fa),.s_cmd_write(fcw),
.s_wdata_valid(fwv),.s_wdata_ready(fwr),.s_wdata(fwdata),.s_wmask(fwmask),
.s_rdata_valid(frv),.s_rdata_ready(frr),.s_rdata(frdata),
.m_cmd_valid(scv),.m_cmd_ready(scr),.m_cmd_address(sa),.m_cmd_write(scw),
.m_wdata_valid(swv),.m_wdata_ready(swr),.m_wdata(swdata),.m_wmask(swmask),
.m_rdata_valid(srv),.m_rdata_ready(srr),.m_rdata(srdata));

arty_ddr_bios core(
.clk(clk),
.ddram_a(ddram_a),
.ddram_ba(ddram_ba),
.ddram_cas_n(ddram_cas_n),
.ddram_cke(ddram_cke),
.ddram_clk_n(ddram_clk_n),
.ddram_clk_p(ddram_clk_p),
.ddram_cs_n(ddram_cs_n),
.ddram_dm(ddram_dm),
.ddram_dq(ddram_dq),
.ddram_dqs_n(ddram_dqs_n),
.ddram_dqs_p(ddram_dqs_p),
.ddram_odt(ddram_odt),
.ddram_ras_n(ddram_ras_n),
.ddram_reset_n(ddram_reset_n),
.ddram_we_n(ddram_we_n),
.init_done(status[0]),
.init_error(status[1]),
.pll_locked(status[2]),
.rst(reset_button),
.sd_io_clk(fclk),
.uart_rx(1'b1),
.uart_tx(bios_tx),
.user_clk(dclk),
.user_port_native_0_cmd_addr(ma),
.user_port_native_0_cmd_ready(mcr),
.user_port_native_0_cmd_valid(mcv),
.user_port_native_0_cmd_we(mcw),
.user_port_native_0_rdata_data(mrdata),
.user_port_native_0_rdata_ready(mrr),
.user_port_native_0_rdata_valid(mrv),
.user_port_native_0_wdata_data(mwdata),
.user_port_native_0_wdata_ready(mwr),
.user_port_native_0_wdata_valid(mwv),
.user_port_native_0_wdata_we(mwmask),
.user_rst(drst)
);
endmodule
