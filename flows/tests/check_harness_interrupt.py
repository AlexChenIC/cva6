# Copyright 2026 OpenHW Foundation
# SPDX-License-Identifier: Apache-2.0
"""Check a built, real harness exits on the first SIGINT during JTAG wait."""

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    log = args.report.with_suffix(".log")
    command = [
        str(args.binary.resolve()),
        "--seed",
        "1",
        "+jtag_rbb_enable=1",
        str(args.elf.resolve()),
    ]
    result = dict(check="jtag-wait-first-sigint", status="fail", command=command)
    process = None
    try:
        with log.open("w") as output:
            process = subprocess.Popen(
                command,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            deadline = time.monotonic() + 20
            while "Attempting to accept client socket" not in log.read_text():
                if process.poll() is not None:
                    raise RuntimeError("Harness exited before entering JTAG wait")
                if time.monotonic() >= deadline:
                    raise RuntimeError("Harness did not enter JTAG wait within 20s")
                time.sleep(0.05)
            started = time.monotonic()
            process.send_signal(signal.SIGINT)
            code = process.wait(timeout=3)
            result.update(
                exit_code=code,
                signal_count=1,
                exit_latency_seconds=time.monotonic() - started,
            )
            if code != 128 + signal.SIGINT:
                raise RuntimeError(f"Expected SIGINT exit 130, got {code}")
            if "*** SUCCESS ***" in log.read_text():
                raise RuntimeError("Interrupted harness printed a success verdict")
            result["status"] = "pass"
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        result["detail"] = str(error)
    finally:
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        args.report.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
