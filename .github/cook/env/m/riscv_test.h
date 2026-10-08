/* Copyright 2026 OpenHW Foundation
 * SPDX-License-Identifier: Apache-2.0
 *
 * Bounded integer CI environment, NOT the riscv-tests p-mode environment.
 * Retain the original instruction assertions but execute in machine mode.
 * No PMP, privilege transition, FP state or VM initialization is performed.
 * Unsupported test categories deliberately have no initialization macro here.
 */
#ifndef COOK_STAGE1_M_RISCV_TEST_H
#define COOK_STAGE1_M_RISCV_TEST_H

#define TESTNUM gp
#define RVTEST_RV32U
#define RVTEST_RV64U

#define RVTEST_CODE_BEGIN \
  .section .text.init; \
  .balign 64; \
  .globl _start; \
_start: \
  li TESTNUM, 0;

#define RVTEST_CODE_END

#define RVTEST_PASS \
  fence; \
  li TESTNUM, 1; \
  la t0, tohost; \
  sw TESTNUM, 0(t0); \
1: j 1b;

#define RVTEST_FAIL \
  bnez TESTNUM, 1f; \
  li TESTNUM, 1; \
1: slli TESTNUM, TESTNUM, 1; \
  ori TESTNUM, TESTNUM, 1; \
  fence; \
  la t0, tohost; \
  sw TESTNUM, 0(t0); \
2: j 2b;

#define RVTEST_DATA_BEGIN \
  .pushsection .tohost,"aw",@progbits; \
  .balign 64; \
  .globl tohost; \
tohost: .dword 0; \
  .globl fromhost; \
fromhost: .dword 0; \
  .popsection; \
  .section .data; \
  .balign 16; \
  .globl begin_signature; \
begin_signature:

#define RVTEST_DATA_END \
  .balign 16; \
  .globl end_signature; \
end_signature:

#endif
