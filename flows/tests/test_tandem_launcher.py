# Copyright 2026 OpenHW Foundation
# SPDX-License-Identifier: Apache-2.0
"""Exercise the child launcher; never change the test runner's resource limits."""

import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from flows.utils import tandem_launcher as launcher


class TandemLauncherTests(unittest.TestCase):
    def test_finite_limit_replaces_small_large_and_unlimited_soft_limits(self):
        for soft in [8192, 1024 * 1024 * 1024, launcher.resource.RLIM_INFINITY]:
            with (
                self.subTest(soft=soft),
                patch.dict(os.environ, {"TANDEM_STACK_KIB": "16384"}),
                patch.object(
                    launcher.resource,
                    "getrlimit",
                    return_value=(soft, launcher.resource.RLIM_INFINITY),
                ),
                patch.object(launcher.resource, "setrlimit") as setter,
            ):
                self.assertEqual(launcher.prepare_stack(), 16384 * 1024)
                setter.assert_called_once_with(
                    launcher.resource.RLIMIT_STACK,
                    (16384 * 1024, launcher.resource.RLIM_INFINITY),
                )

    def test_invalid_settings_fail(self):
        for value in ["0", "-1", "unlimited", "1.5", " 123", "999999999999999999999"]:
            with (
                self.subTest(value=value),
                patch.dict(os.environ, {"TANDEM_STACK_KIB": value}),
            ):
                with self.assertRaises(ValueError):
                    launcher.prepare_stack()

    def test_hard_limit_is_not_raised(self):
        with (
            patch.dict(os.environ, {"TANDEM_STACK_KIB": "16384"}),
            patch.object(launcher.resource, "getrlimit", return_value=(8192, 8192)),
            patch.object(launcher.resource, "setrlimit") as setter,
        ):
            with self.assertRaisesRegex(ValueError, "hard limit"):
                launcher.prepare_stack()
            setter.assert_not_called()

    def test_actual_exec_inherits_finite_limit(self):
        result = subprocess.run(
            [
                sys.executable,
                str(Path(launcher.__file__)),
                sys.executable,
                "-c",
                "import resource; print('child_stack=' + str(resource.getrlimit(resource.RLIMIT_STACK)[0]))",
            ],
            env={**os.environ, "TANDEM_STACK_KIB": "16384"},
            text=True,
            capture_output=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("child_stack=16777216", result.stdout)

    def test_failed_launch_is_nonzero(self):
        result = subprocess.run(
            [sys.executable, str(Path(launcher.__file__)), "/nonexistent/cva6-harness"],
            env={**os.environ, "TANDEM_STACK_KIB": "16384"},
            text=True,
            capture_output=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
