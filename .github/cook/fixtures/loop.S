// Copyright 2026 OpenHW Foundation
// SPDX-License-Identifier: Apache-2.0
// Deliberately never writes tohost. Used only to test interruption handling.
.section .text.init
.globl _start
_start:
  j _start

.section .tohost,"aw",@progbits
.balign 64
.globl tohost
tohost:
  .dword 0
.globl fromhost
fromhost:
  .dword 0
