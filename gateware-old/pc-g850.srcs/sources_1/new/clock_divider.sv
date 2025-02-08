`timescale 1ns / 1ps

module clock_divider #(
    parameter int DIV_BY
) (
    input  wire logic clk,    // Input clock
    output      logic out_clk // Divided clock output
);
    logic [$clog2(DIV_BY)-1:0] cnt = 0;

    always_ff @(posedge clk) begin
        if (cnt != DIV_BY - 1) begin
            out_clk <= 0;
            cnt <= cnt + 1;
        end else begin
            out_clk <= 1;
            cnt <= 0;
        end
    end
endmodule
