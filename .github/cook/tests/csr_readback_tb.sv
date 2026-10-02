// Copyright 2026 OpenHW Foundation
// SPDX-License-Identifier: Apache-2.0 WITH SHL-2.0
`include "rvfi_types.svh"

module csr_readback_tb;
  import ariane_pkg::*;
  localparam config_pkg::cva6_cfg_t Cfg = build_config_pkg::build_config(cva6_config_pkg::cva6_cfg);
  typedef struct packed {
    logic [Cfg.XLEN-1:0] cause, tval;
    logic [Cfg.GPLEN-1:0] tval2;
    logic [31:0] tinst;
    logic gva, valid;
  } exception_t;
  typedef struct packed { logic [Cfg.XLEN-7:0] base; logic [5:0] mode; } jvt_t;
  typedef struct packed {
    logic [Cfg.XLEN-1:0] mie, mip, mideleg, hideleg;
    logic sie, global_enable;
  } irq_t;
  typedef struct packed { logic [Cfg.VLEN-1:0] predict_address; } bp_t;
  typedef struct packed {
    fu_t fu;
    bp_t bp;
    logic [Cfg.VLEN-1:0] pc;
    logic is_compressed;
  } commit_t;
  typedef `RVFI_PROBES_CSR_T(Cfg) probes_t;

  bit clk = 0;
  bit rst_n = 0;
  bit dirty_fp = 0;
  fu_op op = CSR_READ;
  logic [11:0] addr = riscv::CSR_MSTATUS;
  logic [Cfg.XLEN-1:0] wdata = 0, rdata;
  exception_t exception;
  always #5 clk = ~clk;

  csr_regfile #(
    .CVA6Cfg(Cfg), .exception_t(exception_t), .jvt_t(jvt_t),
    .irq_ctrl_t(irq_t), .scoreboard_entry_t(commit_t), .rvfi_probes_csr_t(probes_t)
  ) dut (
    .clk_i(clk), .rst_ni(rst_n), .time_irq_i('0), .commit_instr_i('0),
    .commit_ack_i('0), .boot_addr_i('0), .hart_id_i('0), .ex_i('0),
    .csr_op_i(op), .csr_addr_i(addr), .csr_wdata_i(wdata), .csr_rdata_o(rdata),
    .dirty_fp_state_i(dirty_fp), .csr_write_fflags_i('0), .dirty_v_state_i('0),
    .pc_i('0), .csr_exception_o(exception), .acc_fflags_ex_i('0),
    .acc_fflags_ex_valid_i('0), .csr_hs_ld_st_inst_i('0), .irq_i('0),
    .ipi_i('0), .debug_req_i('0), .perf_data_i('0)
  );

  task automatic write_check(input logic [11:0] csr_addr,
                             input logic [Cfg.XLEN-1:0] value, mask, expected,
                             input string label);
    @(negedge clk);
    addr = csr_addr;
    wdata = value;
    op = CSR_WRITE;
    #1;
    if (exception.valid) $fatal(1, "%s: unexpected write exception", label);
    @(posedge clk);
    #1;
    op = CSR_READ;
    #1;
    if ((rdata & mask) !== expected)
      $fatal(1, "%s: immediate readback got %h expected %h", label, rdata & mask, expected);
    $display("PASS %s: %h", label, rdata & mask);
  endtask

  initial begin
    logic [Cfg.XLEN-1:0] sd;
    sd = {1'b1, {(Cfg.XLEN-1){1'b0}}};
    repeat (3) @(negedge clk);
    rst_n = 1;

    // PMP tests use the CSR interface, not a reimplementation of its WARL logic.
    write_check(riscv::CSR_PMPCFG0, 'h7, 'hff, 'h7, "PMP OFF");
    write_check(riscv::CSR_PMPCFG0, 'h17, 'hff, 'h7, "NA4 retains OFF");
    write_check(riscv::CSR_PMPCFG0, 'h1f, 'hff, Cfg.PMPNapotEn ? 'h1f : 'h7, "NAPOT from OFF");
    write_check(riscv::CSR_PMPCFG0, 'hf, 'hff, 'hf, "PMP TOR");
    write_check(riscv::CSR_PMPCFG0, 'h17, 'hff, 'hf, "NA4 retains TOR");
    write_check(riscv::CSR_PMPCFG0, 'h1f, 'hff, Cfg.PMPNapotEn ? 'h1f : 'hf, "NAPOT from TOR");
    write_check(riscv::CSR_PMPCFG0, 'h8f, 'hff, 'h8f, "PMP lock TOR");
    write_check(riscv::CSR_PMPCFG0, 'h0, 'hff, 'h8f, "PMP locked entry unchanged");

    if (Cfg.FpPresent) begin
      write_check(riscv::CSR_MSTATUS, 'h6000, sd | 'h6000, sd | 'h6000, "FS Dirty sets SD immediately");
      write_check(riscv::CSR_MSTATUS, 'h2000, sd | 'h6000, 'h2000, "FS Initial clears SD immediately");
      @(negedge clk);
      dirty_fp = 1;
      @(posedge clk);
      #1;
      dirty_fp = 0;
      #1;
      if ((rdata & (sd | 'h6000)) !== (sd | 'h6000))
        $fatal(1, "FP dirty input did not set FS and SD together");
      $display("PASS FP dirty input sets FS and SD together");
      if (Cfg.RVS)
        write_check(riscv::CSR_SSTATUS, 0, sd | 'h6000, 0, "SSTATUS clears FS and SD together");
    end else begin
      write_check(riscv::CSR_MSTATUS, 'h6000, sd | 'h6000, 0, "No FP: FS and SD remain zero");
    end
    $display("CSR_READBACK_PASS XLEN=%0d", Cfg.XLEN);
    $finish;
  end
endmodule
