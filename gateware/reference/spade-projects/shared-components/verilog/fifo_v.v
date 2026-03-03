module simple_dual_port_ram #(
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

module async_fifo_v #(
    parameter WIDTH = 8,
    parameter ENTRIES = 4,
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

    simple_dual_port_ram #(
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

module sync_fifo_v #(
    parameter WIDTH = 32,
    parameter ENTRIES = 32768
) (
    input clk,
    input rst,
    input [WIDTH-1:0] din,
    input wput,
    output full,
    output [WIDTH-1:0] dout,
    input rget,
    output empty
);
    localparam ADDR_SIZE = $clog2(ENTRIES);

    reg [ADDR_SIZE-1:0] waddr;
    reg [ADDR_SIZE-1:0] waddr_delay;
    reg [ADDR_SIZE-1:0] raddr;

    wire [ADDR_SIZE-1:0] next_write = waddr + 1'b1;
    wire wrdy = next_write != raddr;
    wire rrdy = raddr != waddr_delay;

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

    simple_dual_port_ram #(
        .WIDTH(WIDTH),
        .ENTRIES(ENTRIES)
    ) ram (
        .wclk(clk),
        .waddr(waddr),
        .write_data(din),
        .write_enable(wput && wrdy),
        .rclk(clk),
        .raddr(ram_raddr),
        .read_data(ram_read_data)
    );

    always @(posedge clk) begin
        if (rst) begin
            waddr <= '0;
            waddr_delay <= '0;
            raddr <= '0;
        end else begin
            waddr_delay <= waddr;
            if (wput && wrdy) begin
                waddr <= waddr + 1'b1;
            end
            if (rget && rrdy) begin
                raddr <= raddr + 1'b1;
            end
        end
    end
endmodule
