module ft_simple_dual_port_ram #(
    parameter WIDTH = 8,
    parameter ENTRIES = 8
) (
    input wclk,
    input [$clog2(ENTRIES)-1:0] waddr,
    input [WIDTH-1:0] write_data,
    input write_enable,
    input rclk,
    input [$clog2(ENTRIES)-1:0] raddr,
    output reg [WIDTH-1:0] read_data
);
    reg [WIDTH-1:0] mem [0:ENTRIES-1];

    always @(posedge wclk) begin
        if (write_enable) begin
            mem[waddr] <= write_data;
        end
    end

    always @(posedge rclk) begin
        read_data <= mem[raddr];
    end
endmodule

module ft_async_fifo #(
    parameter WIDTH = 8,
    parameter ENTRIES = 8,
    parameter SYNC_STAGES = 3
) (
    input wclk,
    input wrst,
    input [WIDTH-1:0] din,
    input wput,
    output full,
    input rclk,
    input rrst,
    output [WIDTH-1:0] dout,
    input rget,
    output empty
);
    localparam ADDR_SIZE = $clog2(ENTRIES);

    reg [ADDR_SIZE-1:0] waddr;
    reg [ADDR_SIZE-1:0] gwsync;
    reg [ADDR_SIZE-1:0] wsync [0:SYNC_STAGES-1];

    reg [ADDR_SIZE-1:0] raddr;
    reg [ADDR_SIZE-1:0] grsync;
    reg [ADDR_SIZE-1:0] rsync [0:SYNC_STAGES-1];

    wire [ADDR_SIZE-1:0] wnext = waddr + 1'b1;
    wire [ADDR_SIZE-1:0] waddr_gray = waddr ^ (waddr >> 1);
    wire [ADDR_SIZE-1:0] wnext_gray = wnext ^ (wnext >> 1);
    wire [ADDR_SIZE-1:0] raddr_gray = raddr ^ (raddr >> 1);

    wire wrdy = wnext_gray != wsync[SYNC_STAGES-1];
    wire rrdy = raddr_gray != rsync[SYNC_STAGES-1];

    reg [ADDR_SIZE-1:0] ram_raddr;
    wire [WIDTH-1:0] ram_read_data;

    assign full = !wrdy;
    assign empty = !rrdy;
    assign dout = ram_read_data;

    always @* begin
        ram_raddr = raddr;
        if (rget && rrdy) begin
            ram_raddr = raddr + 1'b1;
        end
    end

    ft_simple_dual_port_ram #(
        .WIDTH(WIDTH),
        .ENTRIES(ENTRIES)
    ) ram (
        .wclk(wclk),
        .waddr(waddr),
        .write_data(din),
        .write_enable(wput && wrdy),
        .rclk(rclk),
        .raddr(ram_raddr),
        .read_data(ram_read_data)
    );

    integer wi;
    always @(posedge wclk) begin
        if (wrst) begin
            waddr <= '0;
            gwsync <= '0;
            for (wi = 0; wi < SYNC_STAGES; wi = wi + 1) begin
                wsync[wi] <= '0;
            end
        end else begin
            gwsync <= waddr_gray;
            wsync[0] <= grsync;
            for (wi = 1; wi < SYNC_STAGES; wi = wi + 1) begin
                wsync[wi] <= wsync[wi-1];
            end
            if (wput && wrdy) begin
                waddr <= waddr + 1'b1;
            end
        end
    end

    integer ri;
    always @(posedge rclk) begin
        if (rrst) begin
            raddr <= '0;
            grsync <= '0;
            for (ri = 0; ri < SYNC_STAGES; ri = ri + 1) begin
                rsync[ri] <= '0;
            end
        end else begin
            grsync <= raddr_gray;
            rsync[0] <= gwsync;
            for (ri = 1; ri < SYNC_STAGES; ri = ri + 1) begin
                rsync[ri] <= rsync[ri-1];
            end
            if (rget && rrdy) begin
                raddr <= raddr + 1'b1;
            end
        end
    end
endmodule

module ft_u16_v #(
    parameter TX_BUFFER = 64,
    parameter RX_BUFFER = 64,
    parameter PRIORITY_RX = 1,
    parameter PREEMPT = 0
) (
    input clk,
    input rst,

    input ft_clk,
    input ft_rxf,
    input ft_txe,
    input [15:0] ft_data_in,
    input [1:0] ft_be_in,
    output reg [15:0] ft_data_out,
    output reg [1:0] ft_be_out,
    output reg ft_rd,
    output reg ft_wr,
    output reg ft_oe,

    input [15:0] ui_din,
    input [1:0] ui_din_be,
    input ui_din_valid,
    output ui_din_full,

    output [15:0] ui_dout,
    output [1:0] ui_dout_be,
    output ui_dout_empty,
    input ui_dout_get
);
    localparam STATE_IDLE = 2'd0;
    localparam STATE_BUS_SWITCH = 2'd1;
    localparam STATE_READ = 2'd2;
    localparam STATE_WRITE = 2'd3;

    reg [1:0] state_q = STATE_IDLE;
    reg [1:0] state_d;

    wire [17:0] write_fifo_dout;
    wire write_fifo_full;
    wire write_fifo_empty;
    reg write_fifo_rget;

    wire [17:0] read_fifo_dout;
    wire read_fifo_full;
    wire read_fifo_empty;
    reg read_fifo_wput;

    wire can_write = !ft_txe && !write_fifo_empty;
    wire can_read = !ft_rxf && !read_fifo_full;

    assign ui_din_full = write_fifo_full;
    assign ui_dout = read_fifo_dout[15:0];
    assign ui_dout_be = read_fifo_dout[17:16];
    assign ui_dout_empty = read_fifo_empty;

    ft_async_fifo #(
        .WIDTH(18),
        .ENTRIES(TX_BUFFER),
        .SYNC_STAGES(3)
    ) write_fifo (
        .wclk(clk),
        .wrst(rst),
        .din({ui_din_be, ui_din}),
        .wput(ui_din_valid),
        .full(write_fifo_full),
        .rclk(ft_clk),
        .rrst(rst),
        .dout(write_fifo_dout),
        .rget(write_fifo_rget),
        .empty(write_fifo_empty)
    );

    ft_async_fifo #(
        .WIDTH(18),
        .ENTRIES(RX_BUFFER),
        .SYNC_STAGES(3)
    ) read_fifo (
        .wclk(ft_clk),
        .wrst(rst),
        .din({ft_be_in, ft_data_in}),
        .wput(read_fifo_wput),
        .full(read_fifo_full),
        .rclk(clk),
        .rrst(rst),
        .dout(read_fifo_dout),
        .rget(ui_dout_get),
        .empty(read_fifo_empty)
    );

    always @* begin
        reg [1:0] preferred_state;
        reg reading_bus;

        preferred_state = STATE_IDLE;
        if (can_write && ((!PRIORITY_RX) || !can_read)) begin
            preferred_state = STATE_WRITE;
        end
        if (can_read && (PRIORITY_RX || !can_write)) begin
            preferred_state = STATE_BUS_SWITCH;
        end

        write_fifo_rget = 1'b0;
        read_fifo_wput = 1'b0;
        ft_oe = 1'b1;
        ft_rd = 1'b1;
        ft_wr = 1'b1;

        reading_bus = (state_q == STATE_BUS_SWITCH) || (state_q == STATE_READ);
        if (reading_bus) begin
            ft_data_out = {16{1'bz}};
            ft_be_out = {2{1'bz}};
        end else begin
            ft_data_out = write_fifo_dout[15:0];
            ft_be_out = write_fifo_dout[17:16];
        end

        state_d = state_q;
        case (state_q)
            STATE_IDLE: begin
                state_d = preferred_state;
            end
            STATE_BUS_SWITCH: begin
                ft_oe = 1'b0;
                state_d = STATE_READ;
            end
            STATE_READ: begin
                ft_oe = read_fifo_full;
                ft_rd = read_fifo_full;
                read_fifo_wput = !ft_rxf;
                if (ft_rxf || read_fifo_full || (PREEMPT && preferred_state == STATE_WRITE)) begin
                    state_d = preferred_state;
                end
            end
            STATE_WRITE: begin
                ft_wr = write_fifo_empty;
                write_fifo_rget = !ft_txe;
                if (ft_txe || write_fifo_empty || (PREEMPT && preferred_state == STATE_BUS_SWITCH)) begin
                    state_d = preferred_state;
                end
            end
            default: begin
                state_d = STATE_IDLE;
            end
        endcase
    end

    // Match Alchitry Lucid-generated FT state machine behavior:
    // state_q is advanced without an explicit reset branch.
    always @(posedge ft_clk) begin
        state_q <= state_d;
    end
endmodule

// Alchitry PC-G850 bus compatibility profile:
// Lucid instantiates ft with TX_BUFFER=8192 for high burst tolerance.
module ft_u16_v_tx8192 (
    input clk,
    input rst,
    input ft_clk,
    input ft_rxf,
    input ft_txe,
    input [15:0] ft_data_in,
    input [1:0] ft_be_in,
    output [15:0] ft_data_out,
    output [1:0] ft_be_out,
    output ft_rd,
    output ft_wr,
    output ft_oe,
    input [15:0] ui_din,
    input [1:0] ui_din_be,
    input ui_din_valid,
    output ui_din_full,
    output [15:0] ui_dout,
    output [1:0] ui_dout_be,
    output ui_dout_empty,
    input ui_dout_get
);
    ft_u16_v #(
        .TX_BUFFER(8192),
        .RX_BUFFER(64),
        .PRIORITY_RX(1),
        .PREEMPT(0)
    ) impl (
        .clk(clk),
        .rst(rst),
        .ft_clk(ft_clk),
        .ft_rxf(ft_rxf),
        .ft_txe(ft_txe),
        .ft_data_in(ft_data_in),
        .ft_be_in(ft_be_in),
        .ft_data_out(ft_data_out),
        .ft_be_out(ft_be_out),
        .ft_rd(ft_rd),
        .ft_wr(ft_wr),
        .ft_oe(ft_oe),
        .ui_din(ui_din),
        .ui_din_be(ui_din_be),
        .ui_din_valid(ui_din_valid),
        .ui_din_full(ui_din_full),
        .ui_dout(ui_dout),
        .ui_dout_be(ui_dout_be),
        .ui_dout_empty(ui_dout_empty),
        .ui_dout_get(ui_dout_get)
    );
endmodule
