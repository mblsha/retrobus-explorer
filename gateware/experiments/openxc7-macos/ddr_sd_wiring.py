"""Board integration of the Spade DDR UART in the native DDR system clock domain."""


def wiring(native_bist=False, writable=False, sys_clk_freq=83_333_333, fast_sd=False):
    assert sys_clk_freq in (80_000_000, 83_333_333), "Unsupported SD UART clock"
    native = {
        "cmd_addr": "ma",
        "cmd_ready": "mcr",
        "cmd_valid": "mcv",
        "cmd_we": "mcw",
        "rdata_data": "mrdata",
        "rdata_ready": "mrr",
        "rdata_valid": "mrv",
        "wdata_data": "mwdata",
        "wdata_ready": "mwr",
        "wdata_valid": "mwv",
        "wdata_we": "mwmask",
    }
    connections = {"user_port_native_0_" + k: v for k, v in native.items()}
    connections.update(
        uart_rx="1'b1", uart_tx="bios_tx", user_clk="dclk", user_rst="drst"
    )
    text = """
wire dclk,drst;
wire bios_tx,sd_tx;
wire [6:0] sd_status_selector;
// Both UARTs idle high. Read BIOS boot at 115200; use the Spade loader at
// 1 Mbaud after boot output has stopped. Do not send loader packets during boot.
assign usb_tx = bios_tx & sd_tx;
wire mcv,mcr,mcw,mwv,mwr,mrv,mrr;
wire [23:0] ma;
wire [127:0] mwdata,mrdata;
wire [15:0] mwmask;
wire co,ce,armed;
wire [3:0] dout,doe;
ddr_uart sd(
.writable(1'b0),.dat_in({pmod[1],pmod[0],pmod[7],pmod[3]}),
.clk(dclk),.rst(drst),.initialized(status[0] && !status[1]),.diagnostic_status(27'd0),.status_selector(sd_status_selector),.usb_rx(usb_rx),.usb_tx(sd_tx),
.ddr_cmd_valid(mcv),.ddr_cmd_ready(mcr),.ddr_cmd_address(ma),.ddr_cmd_write(mcw),
.ddr_wdata_valid(mwv),.ddr_wdata_ready(mwr),.ddr_wdata(mwdata),.ddr_wdata_mask(mwmask),
.ddr_rdata_valid(mrv),.ddr_rdata_ready(mrr),.ddr_rdata(mrdata),
.sd_clk(pmod[6]),.cmd_in(pmod[2]),.cmd_out(co),.cmd_oe(ce),
.dat_out(dout),.dat_oe(doe),.armed_status(armed));
assign pmod[2] = ce ? co : 1'bz;
assign pmod[3] = doe[0] ? dout[0] : 1'bz;
assign pmod[7] = doe[1] ? dout[1] : 1'bz;
assign pmod[0] = doe[2] ? dout[2] : 1'bz;
assign pmod[1] = doe[3] ? dout[3] : 1'bz;
"""
    if native_bist:
        import re

        text = re.sub(
            r"\b(" + "|".join(native.values()) + r")\b",
            lambda m: "s" + m.group()[1:],
            text,
        )
        text = text.replace(
            ".initialized(status[0] && !status[1]),.diagnostic_status(27'd0),.status_selector(sd_status_selector)",
            ".initialized(bist_passed),.diagnostic_status(bist_status_mux),.status_selector(sd_status_selector)",
        )
        text += """
wire mcv,mcr,mcw,mwv,mwr,mrv,mrr;
wire [23:0] ma;
wire [127:0] mwdata,mrdata;
wire [15:0] mwmask;
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
.cmd_valid(mcv),.cmd_ready(mcr),.cmd_address(ma),.cmd_write(mcw),
.wdata_valid(mwv),.wdata_ready(mwr),.wdata(mwdata),.wdata_mask(mwmask),
.rdata_valid(mrv),.rdata_ready(mrr),.rdata(mrdata),
.client_cmd_valid(scv),.client_cmd_ready(scr),.client_cmd_address(sa),.client_cmd_write(scw),
.client_wdata_valid(swv),.client_wdata_ready(swr),.client_wdata(swdata),.client_wdata_mask(swmask),
.client_rdata_valid(srv),.client_rdata_ready(srr),.client_rdata(srdata),
.busy(bist_busy),.passed(bist_passed),.failed(bist_failed),.progress(bist_progress),.diagnostic(bist_diagnostic),.expected_word(bist_expected),.actual_word(bist_actual));
"""
        text += "\nalways @* begin\ncase (sd_status_selector)\n"
        text += "0: bist_status_mux = {bist_diagnostic,bist_progress[23:5],bist_failed,bist_passed,bist_busy};\n"
        for selector in range(1, 12):
            text += f"{selector}: bist_status_mux = bist_detail[{(selector - 1) * 27} +: 27];\n"
        text += "120: bist_status_mux = {11'd0,sd_peak_edges};\n121: bist_status_mux = {3'd0,sd_minimum_period};\n122: bist_status_mux = {3'd0,sd_latest_period};\n123: bist_status_mux = sd_total_edges[26:0];\n124: bist_status_mux = {22'd0,sd_total_edges[31:27]};\n127: bist_status_mux = 27'h534244;\ndefault: bist_status_mux = 0;\nendcase\nend\n"
        text = re.sub(
            r"\b(" + "|".join(native.values()) + r")\b",
            lambda m: "p" + m.group()[1:],
            text,
        )
        text += """
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
"""
    if writable:
        assert native_bist, "Writable SD requires full DDR qualification and zeroing"
        text = text.replace(".writable(1'b0)", ".writable(1'b1)")
    text = text.replace("17'd80000", f"17'd{sys_clk_freq // 1000}")
    if sys_clk_freq == 80_000_000:
        text = text.replace("ddr_uart sd(", "ddr_uart_80 sd(")
    if fast_sd:
        assert native_bist, "Fast SD requires native qualification"
        import re

        frontend, rest = text.split("assign pmod[2]", 1)
        frontend = re.sub(
            r"\b(scv|scr|scw|swv|swr|srv|srr|sa|swdata|srdata|swmask)\b",
            lambda m: "f" + m.group()[1:],
            frontend,
        )
        frontend = frontend.replace("ddr_uart_80 sd(", "ddr_uart_100 sd(")
        frontend = frontend.replace("ddr_uart sd(", "ddr_uart_100 sd(")
        frontend = frontend.replace(".clk(dclk),.rst(drst)", ".clk(fclk),.rst(frst)")
        frontend = frontend.replace(
            ".initialized(bist_passed)", ".initialized(fast_passed[1])"
        )
        frontend = frontend.replace(
            ".diagnostic_status(bist_status_mux)", ".diagnostic_status(fast_status)"
        )
        text = frontend + "assign pmod[2]" + rest
        text = text.replace("case (sd_status_selector)", "case (slow_selector)")
        text += """
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
"""
        connections["sd_io_clk"] = "fclk"
    return text, connections
