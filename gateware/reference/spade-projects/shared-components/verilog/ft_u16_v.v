// Depends on shared async_fifo_v from fifo_v.v.

module ft_v #(
    parameter DATA_WIDTH = 16,
    parameter BE_WIDTH = 2,
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
    input [DATA_WIDTH-1:0] ft_data_in,
    input [BE_WIDTH-1:0] ft_be_in,
    output reg [DATA_WIDTH-1:0] ft_data_out,
    output reg [BE_WIDTH-1:0] ft_be_out,
    output reg ft_rd,
    output reg ft_wr,
    output reg ft_oe,

    input [DATA_WIDTH-1:0] ui_din,
    input [BE_WIDTH-1:0] ui_din_be,
    input ui_din_valid,
    output ui_din_full,

    output [DATA_WIDTH-1:0] ui_dout,
    output [BE_WIDTH-1:0] ui_dout_be,
    output ui_dout_empty,
    input ui_dout_get
);
    localparam STATE_IDLE = 2'd0;
    localparam STATE_BUS_SWITCH = 2'd1;
    localparam STATE_READ = 2'd2;
    localparam STATE_WRITE = 2'd3;
    localparam FIFO_WIDTH = DATA_WIDTH + BE_WIDTH;

    reg [1:0] state_q = STATE_IDLE;
    reg [1:0] state_d;

    wire [FIFO_WIDTH-1:0] write_fifo_dout;
    wire write_fifo_full;
    wire write_fifo_empty;
    reg write_fifo_rget;

    wire [FIFO_WIDTH-1:0] read_fifo_dout;
    wire read_fifo_full;
    wire read_fifo_empty;
    reg read_fifo_wput;

    wire can_write = !ft_txe && !write_fifo_empty;
    wire can_read = !ft_rxf && !read_fifo_full;

    assign ui_din_full = write_fifo_full;
    assign ui_dout = read_fifo_dout[DATA_WIDTH-1:0];
    assign ui_dout_be = read_fifo_dout[FIFO_WIDTH-1:DATA_WIDTH];
    assign ui_dout_empty = read_fifo_empty;

    async_fifo_v #(
        .WIDTH(FIFO_WIDTH),
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

    async_fifo_v #(
        .WIDTH(FIFO_WIDTH),
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
            ft_data_out = {DATA_WIDTH{1'bz}};
            ft_be_out = {BE_WIDTH{1'bz}};
        end else begin
            ft_data_out = write_fifo_dout[DATA_WIDTH-1:0];
            ft_be_out = write_fifo_dout[FIFO_WIDTH-1:DATA_WIDTH];
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

// Temporary compatibility shim for legacy references to ft_u16_v.
module ft_u16_v #(
    parameter DATA_WIDTH = 16,
    parameter BE_WIDTH = 2,
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
    input [DATA_WIDTH-1:0] ft_data_in,
    input [BE_WIDTH-1:0] ft_be_in,
    output [DATA_WIDTH-1:0] ft_data_out,
    output [BE_WIDTH-1:0] ft_be_out,
    output ft_rd,
    output ft_wr,
    output ft_oe,

    input [DATA_WIDTH-1:0] ui_din,
    input [BE_WIDTH-1:0] ui_din_be,
    input ui_din_valid,
    output ui_din_full,

    output [DATA_WIDTH-1:0] ui_dout,
    output [BE_WIDTH-1:0] ui_dout_be,
    output ui_dout_empty,
    input ui_dout_get
);
    ft_v #(
        .DATA_WIDTH(DATA_WIDTH),
        .BE_WIDTH(BE_WIDTH),
        .TX_BUFFER(TX_BUFFER),
        .RX_BUFFER(RX_BUFFER),
        .PRIORITY_RX(PRIORITY_RX),
        .PREEMPT(PREEMPT)
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
