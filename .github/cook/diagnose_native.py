#!/usr/bin/env python3
"""Preserve a failed native command and obtain a bounded debugger backtrace."""

import json
import os
from pathlib import Path
import resource
import subprocess


def main():
    root = Path.cwd()
    output = root / "ci-results" / "native-diagnostic"
    output.mkdir(parents=True, exist_ok=True)
    commands = sorted(root.glob("build/*/simulation/*/*/simulation.command.json"))
    if not commands:
        print("No native simulation command to diagnose")
        return
    command = json.loads(commands[0].read_text())
    if isinstance(command, dict):
        command = command["argv"]
    (output / "command.json").write_text(json.dumps(command, indent=2) + "\n")
    (output / "stack-limit.json").write_text(
        json.dumps(resource.getrlimit(resource.RLIMIT_STACK))
    )
    with (output / "libraries.txt").open("w") as log:
        subprocess.run(
            ["ldd", command[0]],
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=20,
        )
    for label, limit in (("default-stack", None), ("64m-stack", 64 * 1024 * 1024)):
        directory = output / label
        directory.mkdir(exist_ok=True)
        if limit is not None:
            _, hard = resource.getrlimit(resource.RLIMIT_STACK)
            resource.setrlimit(resource.RLIMIT_STACK, (limit, hard))
        with (directory / "gdb.log").open("w") as log:
            try:
                subprocess.run(
                    [
                        "gdb",
                        "-batch",
                        "-ex",
                        "set pagination off",
                        "-ex",
                        "set print frame-arguments none",
                        "-ex",
                        "run",
                        "-ex",
                        "thread apply all bt 30",
                        "--args",
                        *command,
                    ],
                    cwd=directory,
                    env=os.environ.copy(),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=False,
                    timeout=120,
                )
            except subprocess.TimeoutExpired:
                log.write("\nDiagnostic timed out\n")
        print((directory / "gdb.log").read_text(errors="replace")[-20000:])


if __name__ == "__main__":
    main()
