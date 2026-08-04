#!/usr/bin/env python3
# Copyright 2026 OpenHW Group
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

"""Extract actionable failure lines from cook.py and simulator logs."""

from __future__ import annotations

import argparse
from pathlib import Path
import re

FAILURE_PATTERNS = (
    re.compile(r"\[FAILED\]"),
    re.compile(r"\bSIMULATION FAILED\b"),
    re.compile(r"\bERROR\s+return code:"),
    re.compile(r":\s+FAIL\s+\([1-9][0-9]*\)\s*$"),
    re.compile(r"\bbad syscall\b", re.IGNORECASE),
    re.compile(r"\bunrecognized opcode\b", re.IGNORECASE),
    re.compile(r"\bextension .+ required\b", re.IGNORECASE),
    re.compile(r"\*{3}\s+FAILED\s+\*{3}"),
)


def summarize(paths: list[Path]) -> list[str]:
    matches: list[str] = []
    for path in paths:
        if not path.is_file():
            continue
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
        ):
            if any(pattern.search(line) for pattern in FAILURE_PATTERNS):
                matches.append(f"{path}:{line_number}:{line}")
    return matches


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("logs", nargs="+", type=Path)
    args = parser.parse_args()

    matches = summarize(args.logs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(f"{match}\n" for match in matches), encoding="utf-8")
    if matches:
        print("\n".join(matches))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
