// Same-clock true dual-port memory. Controllers must exclude simultaneous
// writes to the same address and read/write collisions across the two ports.
// No reset clears memory: reset/disarm releases I/O while preserving uploads.
module card_memory_v #(parameter ADDR_BITS = 14) (
    input clk,
    input [ADDR_BITS-1:0] a_addr,
    input [7:0] a_data,
    input a_write,
    output reg [7:0] a_read,
    input [ADDR_BITS-1:0] b_addr,
    input [7:0] b_data,
    input b_write,
    output reg [7:0] b_read
);
    (* ram_style = "block" *) reg [7:0] memory [0:(1 << ADDR_BITS)-1];
    integer i;
    initial begin
        for (i = 0; i < (1 << ADDR_BITS); i = i + 1) memory[i] = 0;
    end
    always @(posedge clk) begin
        if (a_write) memory[a_addr] <= a_data;
        a_read <= memory[a_addr];
    end
    always @(posedge clk) begin
        if (b_write) memory[b_addr] <= b_data;
        b_read <= memory[b_addr];
    end
endmodule
