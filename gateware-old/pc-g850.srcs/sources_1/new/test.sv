`timescale 1ns / 1ps

module test(
  input wire in,
  output logic out
    );
    
  always_comb begin
    out = !in;
  end
endmodule
