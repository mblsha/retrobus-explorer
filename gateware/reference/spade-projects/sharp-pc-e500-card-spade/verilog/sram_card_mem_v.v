module sram_card_mem_v (
    input wire clk,
    input wire rst,
    input wire [10:0] waddr,
    input wire [7:0] din,
    input wire we,
    input wire [10:0] bus_raddr,
    output wire [7:0] bus_dout,
    input wire [10:0] uart_raddr,
    output wire [7:0] uart_dout
);
    (* ram_style = "distributed" *) reg [7:0] mem [0:2047];
    integer i;

    initial begin
        for (i = 0; i < 2048; i = i + 1) begin
            mem[i] = 8'h00;
        end
    end

    always @(posedge clk) begin
        if (we) begin
            mem[waddr] <= din;
        end
    end

    assign bus_dout = mem[bus_raddr];
    assign uart_dout = mem[uart_raddr];
endmodule
