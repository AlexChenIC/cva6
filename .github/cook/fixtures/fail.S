# Copyright 2026 OpenHW Foundation
# SPDX-License-Identifier: Apache-2.0
# Infrastructure control: intentional failed test 1, not an ISA testcase.
.section .text.init
.globl _start
_start:
  li t0, 3
  la t1, tohost
  sw t0, 0(t1)
1: j 1b

.section .tohost,"aw",@progbits
.balign 64
.globl tohost
tohost: .dword 0
.globl fromhost
fromhost: .dword 0
