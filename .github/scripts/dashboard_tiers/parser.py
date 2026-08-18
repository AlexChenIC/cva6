#!/usr/bin/env python3
# Copyright 2026 OpenHW Group
# SPDX-License-Identifier: Apache-2.0
"""Parse Tier CI job names used by the dashboard."""

import re


SKIP_JOBS = {
    "Setup Tools",
    "Test Summary",
    "Resolve Tier",
    "Prepare Matrix",
    "setup-tools",
    "report-summary",
}


def parse_job_name(job_name: str, _workflow_name: str) -> dict[str, str] | None:
    name = job_name.strip()
    if name in SKIP_JOBS:
        return None

    match = re.fullmatch(r"RV(32|64)\s+Tier[12]\s+(.+?)\s+/\s+(.+)", name)
    if not match:
        return None

    arch, config, testcase = match.groups()
    if "${{" in config or "${{" in testcase:
        return None

    return {
        "arch": f"rv{arch}",
        "config": config.strip(),
        "testcase": testcase.strip(),
    }
