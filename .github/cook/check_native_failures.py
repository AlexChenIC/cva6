# Copyright 2026 OpenHW Foundation
# SPDX-License-Identifier: Apache-2.0
"""Exercise real TestHarness failures; these are not architectural test cases."""

import json
import os
from pathlib import Path
import signal
import subprocess
import time

import yaml

from flows.recipes.verilator_testharness_comp import testharness_binary
from flows.recipes.verilator_testharness_run import (
    read_tandem_report,
    run_test,
    run_testharness_and_trace,
    runtime_environment,
    testharness_command,
    testharness_log_passed,
)
from flows.utils.utils import CompMode, TraceMode


def check_native_failures(root, target, config, names, cook, run):
    output = root / "ci-results" / "native-negative"
    output.mkdir(parents=True)
    results = {"status": "FAIL", "checks": {}}
    try:
        # Build a separate non-terminating program through the public Cook recipe.
        run(
            "compile-negative-loop",
            cook
            + [
                "sw-compile",
                "-t",
                target,
                "-c",
                "github_actions_gcc",
                "--out",
                "ci-loop",
                "--march",
                config["march"],
                "--mabi",
                config["mabi"],
                "--linker",
                f"config/target/{target}/link.ld",
                "--options",
                "nostdlib",
                "--options",
                "nostartfiles",
                "--options",
                "static",
                ".github/cook/fixtures/loop.S",
                "--quiet",
            ],
        )
        binary = testharness_binary(root, target, CompMode.rtl, True)
        compile_root = root / "build" / target / "compile"
        loop = compile_root / "ci-loop" / "ci-loop.elf"
        tohost = (compile_root / "ci-loop" / "ci-loop.add_tohost").read_text().strip()
        env, spike = runtime_environment(root, target)
        command = testharness_command(
            binary, loop, target=target, tohost=tohost, trace_mode=TraceMode.notrace
        )

        directory = output / "sigterm"
        directory.mkdir()
        (directory / "command.json").write_text(json.dumps(command, indent=2) + "\n")
        with (directory / "testharness.log").open("w") as log:
            process = subprocess.Popen(
                command,
                cwd=directory,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                time.sleep(2)
                if process.poll() is not None:
                    raise ValueError(
                        "Non-terminating ELF exited before signal injection"
                    )
                process.send_signal(signal.SIGTERM)
                code = process.wait(timeout=15)
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
        text = (directory / "testharness.log").read_text(errors="replace")
        if (
            code != 128 + signal.SIGTERM
            or "interrupted by signal 15" not in text
            or testharness_log_passed(directory / "testharness.log")[0]
        ):
            raise ValueError(f"SIGTERM was not classified by the TestHarness: {code}")
        results["checks"]["sigterm"] = {
            "status": "PASS",
            "actual_exit_code": code,
            "expected_simulation": "FAIL",
        }

        passed, detail, directory = run_test(
            target=target,
            test_name="ci-loop",
            comp_mode=CompMode.rtl,
            trace_mode=TraceMode.notrace,
            iss_enabled=False,
            interactive_gui=False,
            timeout=2,
            tandem_enabled=True,
        )
        execution = yaml.safe_load((directory / "execution.yml").read_text())
        if (
            passed
            or execution != {"exit_code": 124, "timed_out": True}
            or "timed out" not in detail
        ):
            raise ValueError(f"Cook timeout was not rejected: {detail}")
        results["checks"]["timeout"] = {
            "status": "PASS",
            "execution": execution,
            "expected_simulation": "FAIL",
            "detail": detail,
        }

        # Keep RTL/FESVR on the first genuine test; load the second ELF only
        # into Spike. The native rvfi_compare scoreboard must detect divergence.
        directory = output / "mismatch"
        directory.mkdir()
        first, second = names[:2]
        elf = compile_root / first / f"{first}.elf"
        other = compile_root / second / f"{second}.elf"
        tohost = (compile_root / first / f"{first}.add_tohost").read_text().strip()
        command = testharness_command(
            binary, elf, target=target, tohost=tohost, trace_mode=TraceMode.notrace
        )
        command = [
            f"+elf_file={other}" if part.startswith("+elf_file=") else part
            for part in command
        ]
        passed, detail = run_testharness_and_trace(
            command=command,
            output_dir=directory,
            env=env,
            spike_install=spike,
            compiler_isa=config["march"],
            timeout=30,
            tandem_enabled=True,
        )
        report = yaml.safe_load((directory / "testharness.log.yaml").read_text())
        if (
            passed
            or type(report.get("mismatches_count")) is not int
            or report["mismatches_count"] < 1
        ):
            raise ValueError(f"Controlled mismatch was not detected: {detail}")
        try:
            read_tandem_report(directory / "testharness.log.yaml")
        except ValueError:
            pass
        else:
            raise ValueError("Native mismatch report passed the acceptance validator")
        results["checks"]["mismatch"] = {
            "status": "PASS",
            "mismatches_count": report["mismatches_count"],
            "expected_simulation": "FAIL",
            "detail": detail,
        }
        results["status"] = "PASS"
        return results
    finally:
        (output / "evidence.json").write_text(json.dumps(results, indent=2) + "\n")
