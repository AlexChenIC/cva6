# Copyright 2026 OpenHW Group
# SPDX-License-Identifier: Apache-2.0 WITH SHL-2.0

"""Exercise real subprocess failure, file logging, and timeout behavior."""

import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from flows.utils.logged_process import (
    run_logged_process,
)  # pylint: disable=wrong-import-position


class LoggedProcessTest(unittest.TestCase):
    def test_exit_status_and_both_output_streams_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "process.log"
            rc, timed_out = run_logged_process(
                [
                    sys.executable,
                    "-c",
                    "import sys; print('out'); print('err', file=sys.stderr); sys.exit(7)",
                ],
                cwd=root,
                env=os.environ.copy(),
                log=log,
                timeout=5,
            )
            self.assertEqual((rc, timed_out), (7, False))
            self.assertIn("out", log.read_text())
            self.assertIn("err", log.read_text())

    @unittest.skipUnless(os.name == "posix", "POSIX process group test")
    def test_silent_child_process_is_terminated_on_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child = "import time; from pathlib import Path; time.sleep(1); Path('survived').touch()"
            parent = f"import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', {child!r}]); print('ready', flush=True); time.sleep(60)"
            start = time.monotonic()
            rc, timed_out = run_logged_process(
                [sys.executable, "-c", parent],
                cwd=root,
                env=os.environ.copy(),
                log=root / "log",
                timeout=0.3,
            )
            self.assertEqual((rc, timed_out), (124, True))
            self.assertLess(time.monotonic() - start, 5)
            self.assertIn("ready", (root / "log").read_text())
            time.sleep(1.1)
            self.assertFalse((root / "survived").exists())

    def test_launch_failure_is_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(FileNotFoundError):
                run_logged_process(
                    [str(root / "absent")],
                    cwd=root,
                    env=os.environ.copy(),
                    log=root / "log",
                    timeout=1,
                )


if __name__ == "__main__":
    unittest.main()
