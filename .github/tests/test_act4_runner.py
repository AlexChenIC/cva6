# Copyright 2026 OpenHW Group
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock

from flows.act4.corpus import CorpusTest, PreparedTest
from flows.act4 import runner


class Act4RunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.elf = self.root / "I-add-01.elf"
        self.elf.write_bytes(b"ELF fixture")
        spec = CorpusTest(
            test_id="I-add-01",
            elf="elfs/I-add-01.elf",
            sha256=hashlib.sha256(b"ELF fixture").hexdigest(),
            size=len(b"ELF fixture"),
            source="I-add-01.S",
        )
        self.test = PreparedTest(spec=spec, path=self.elf)
        self.log = self.root / "test.log"

    def write_log(self, *lines: str) -> None:
        self.log.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def success_line(self, elf: Path | None = None) -> str:
        return f"{elf or self.elf} *** SUCCESS *** (tohost = 0) after 123 cycles"

    def write_executable(self, body: str) -> Path:
        executable = self.root / "testharness-fixture.py"
        executable.write_text("#!/usr/bin/env python3\n" + body, encoding="utf-8")
        executable.chmod(0o755)
        return executable

    def test_exact_current_elf_marker_passes_without_rvcp(self) -> None:
        self.write_log(self.success_line())

        passed, detail = runner.evaluate_log(self.test, self.log, 0, False)

        self.assertTrue(passed, detail)
        self.assertIn("RVCP summary absent", detail)

    def test_exact_rvcp_summary_is_bound_to_current_source(self) -> None:
        self.write_log(
            self.success_line(),
            'RVCP-SUMMARY: TEST PASSED - Test File "I-add-01.S"',
        )

        passed, detail = runner.evaluate_log(self.test, self.log, 0, False)

        self.assertTrue(passed, detail)
        self.assertIn("RVCP", detail)

    def test_success_for_another_elf_cannot_pass(self) -> None:
        self.write_log(self.success_line(self.root / "wrong.elf"))

        passed, detail = runner.evaluate_log(self.test, self.log, 0, False)

        self.assertFalse(passed)
        self.assertIn("current ELF", detail)

    def test_duplicate_success_markers_cannot_pass(self) -> None:
        self.write_log(self.success_line(), self.success_line())

        passed, detail = runner.evaluate_log(self.test, self.log, 0, False)

        self.assertFalse(passed)
        self.assertIn("found 2", detail)

    def test_failure_markers_override_success(self) -> None:
        self.write_log(
            self.success_line(),
            f"{self.elf} *** FAILED *** (tohost = 2147483647) after 999 cycles",
            "UVM_FATAL failure",
            "WARNING: No valid address of 'tohost'",
        )

        passed, detail = runner.evaluate_log(self.test, self.log, 0, False)

        self.assertFalse(passed)
        self.assertIn("TestHarness failure marker", detail)
        self.assertIn("No valid address", detail)

    def test_wrong_or_duplicate_rvcp_summary_cannot_pass(self) -> None:
        self.write_log(
            self.success_line(),
            'RVCP-SUMMARY: TEST PASSED - Test File "other.S"',
        )
        passed, detail = runner.evaluate_log(self.test, self.log, 0, False)
        self.assertFalse(passed)
        self.assertIn("current test", detail)

        self.write_log(
            self.success_line(),
            'RVCP-SUMMARY: TEST PASSED - Test File "I-add-01.S"',
            'RVCP-SUMMARY: TEST FAILED - Test File "I-add-01.S"',
        )
        passed, detail = runner.evaluate_log(self.test, self.log, 0, False)
        self.assertFalse(passed)
        self.assertIn("found 2", detail)

    def test_nonzero_return_and_wall_timeout_cannot_pass(self) -> None:
        self.write_log(self.success_line())
        passed, detail = runner.evaluate_log(self.test, self.log, 7, False)
        self.assertFalse(passed)
        self.assertIn("returned 7", detail)

        passed, detail = runner.evaluate_log(self.test, self.log, -15, True)
        self.assertFalse(passed)
        self.assertIn("wall-clock timeout", detail)

    def test_run_command_uses_elf_file_and_real_rtl_timeout(self) -> None:
        executable = self.write_executable(
            "import os, sys\n"
            "if os.environ.get('SPIKE_TANDEM'):\n"
            "    raise SystemExit(9)\n"
            "elf = sys.argv[1]\n"
            "print(f'{elf} *** SUCCESS *** (tohost = 0) after 12 cycles')\n"
            "print('RVCP-SUMMARY: TEST PASSED - Test File \"I-add-01.S\"')\n"
        )

        result = runner.run_test(
            executable,
            self.test,
            self.root / "logs",
            cycle_timeout=456,
            wall_timeout_seconds=5,
            cwd=self.root,
            environment={"SPIKE_TANDEM": "1"},
        )

        self.assertTrue(result.passed, result.detail)
        self.assertIn(f"+elf_file={self.elf}", result.command)
        self.assertIn("+time_out=456", result.command)
        self.assertIn("+debug_disable=1", result.command)
        self.assertFalse(any("max-cycles" in value for value in result.command))

    def test_wall_timeout_terminates_testharness(self) -> None:
        executable = self.write_executable("import time\ntime.sleep(60)\n")

        result = runner.run_test(
            executable,
            self.test,
            self.root / "logs",
            cycle_timeout=456,
            wall_timeout_seconds=0.1,
            cwd=self.root,
        )

        self.assertFalse(result.passed)
        self.assertTrue(result.timed_out)
        self.assertLess(result.duration_seconds, 5)

    def test_process_group_kills_child_after_leader_exits(self) -> None:
        child_pid_file = self.root / "child.pid"
        executable = self.write_executable(
            "import pathlib, signal, subprocess, sys, time\n"
            "child_code = (\n"
            "    'import os, pathlib, signal, sys, time; '\n"
            "    'signal.signal(signal.SIGTERM, signal.SIG_IGN); '\n"
            "    'pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); '\n"
            "    'time.sleep(60)'\n"
            ")\n"
            f"subprocess.Popen([sys.executable, '-c', child_code, {str(child_pid_file)!r}])\n"
            f"while not pathlib.Path({str(child_pid_file)!r}).exists(): time.sleep(0.01)\n"
            "time.sleep(60)\n"
        )

        result = runner.run_test(
            executable,
            self.test,
            self.root / "logs",
            cycle_timeout=456,
            wall_timeout_seconds=1.0,
            cwd=self.root,
        )

        self.assertTrue(result.timed_out)
        child_pid = int(child_pid_file.read_text(encoding="utf-8"))
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            try:
                os.kill(child_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        else:
            self.fail(f"timed-out TestHarness child {child_pid} survived cleanup")

    def test_zero_test_corpus_is_rejected(self) -> None:
        empty = Mock()
        empty.tests = ()

        with self.assertRaisesRegex(runner.RunnerError, "zero-test"):
            runner.run_corpus(
                empty,
                self.root / "unused",
                self.root / "logs",
                cycle_timeout=1,
                wall_timeout_seconds=1,
                cwd=self.root,
            )


if __name__ == "__main__":
    unittest.main()
