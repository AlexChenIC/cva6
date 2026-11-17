# Copyright 2026 OpenHW Foundation
# SPDX-License-Identifier: Apache-2.0
"""Set a finite stack in this simulation child, then replace it with the harness."""

import os
import re
import sys

try:
    import resource
except ImportError:
    resource = None


def prepare_stack():
    if resource is None:
        raise OSError("Live tandem requires POSIX stack resource limits")
    raw = os.environ.get("TANDEM_STACK_KIB", "262144")
    if not re.fullmatch(r"[1-9][0-9]*", raw):
        raise ValueError("TANDEM_STACK_KIB must be a positive finite integer")
    required = int(raw) * 1024
    if required > sys.maxsize:
        raise ValueError("TANDEM_STACK_KIB exceeds the host resource-limit range")
    soft, hard = resource.getrlimit(resource.RLIMIT_STACK)
    if hard != resource.RLIM_INFINITY and required > hard:
        raise ValueError("TANDEM_STACK_KIB exceeds the stack hard limit")
    if soft != required:
        resource.setrlimit(resource.RLIMIT_STACK, (required, hard))
    return required


def main():
    if len(sys.argv) < 2:
        print("Missing live TestHarness command", file=sys.stderr)
        return 2
    try:
        required = prepare_stack()
        print(f"Live tandem stack soft limit: {required} bytes", flush=True)
        os.execvp(sys.argv[1], sys.argv[1:])
    except (OSError, ValueError, OverflowError) as error:
        print(f"Cannot launch live TestHarness: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
