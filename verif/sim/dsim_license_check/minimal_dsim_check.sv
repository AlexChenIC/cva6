`timescale 1ns/1ps

module minimal_dsim_check;
  initial begin
    $display("DSim license check");
    #1 $finish;
  end
endmodule
