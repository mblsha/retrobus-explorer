module card_ram_2k_v (
    input wire clk,
    input wire rst,
    input wire [10:0] waddr,
    input wire [7:0] din,
    input wire we,
    input wire [10:0] raddr,
    output wire [7:0] dout
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

    assign dout = mem[raddr];

    wire _unused = rst;
endmodule
