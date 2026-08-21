"""Execute integrity-verified ACT4 ELFs with the standalone CVA6 TestHarness.

This module intentionally has no Sail or Spike integration.  ACT4 expected
results are already embedded in each frozen self-checking ELF.  Runtime success
therefore requires the TestHarness exit code and a log marker bound to the
exact ELF being executed; broad searches for the word ``PASSED`` are never
accepted.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import time
from typing import Mapping

from flows.act4.corpus import PreparedCorpus, PreparedTest

_ANY_SUCCESS_RE = re.compile(
    r"^.+ \*\*\* SUCCESS \*\*\* \(tohost = 0\) after [0-9]+ cycles$"
)
_ANY_TOHOST_FAILURE_RE = re.compile(
    r"^.+ \*\*\* FAILED \*\*\* \(tohost = [^)]+\) after [0-9]+ cycles$"
)
_RVCP_PREFIX = "RVCP-SUMMARY:"
_FAILURE_MARKERS = (
    "*** FAILED ***",
    "SIMULATION FAILED",
    "UVM_ERROR",
    "UVM_FATAL",
    "WARNING: No valid address of 'tohost'",
)


class RunnerError(RuntimeError):
    """The corpus cannot be executed safely."""


@dataclass(frozen=True)
class TestResult:
    """Fail-closed result for one manifest entry."""

    test_id: str
    elf: str
    passed: bool
    detail: str
    return_code: int | None
    timed_out: bool
    duration_seconds: float
    log_path: Path
    command: tuple[str, ...]


def _expected_success_pattern(elf: Path) -> re.Pattern[str]:
    return re.compile(
        rf"^{re.escape(str(elf))} \*\*\* SUCCESS \*\*\* "
        r"\(tohost = 0\) after [0-9]+ cycles$"
    )


def evaluate_log(
    test: PreparedTest,
    log_path: Path,
    return_code: int | None,
    timed_out: bool,
) -> tuple[bool, str]:
    """Evaluate one TestHarness log against the exact current ELF contract.

    RVCP summaries are optional in the first frozen-corpus runtime version.
    When any RVCP summary is present, however, there must be exactly one and it
    must be the PASSED line for this manifest entry's source file.
    """

    reasons: list[str] = []
    if timed_out:
        reasons.append("wall-clock timeout")
    if return_code is None:
        reasons.append("TestHarness did not start")
    elif return_code != 0:
        reasons.append(f"TestHarness returned {return_code}")

    expected_success = _expected_success_pattern(test.path)
    expected_success_count = 0
    all_success_count = 0
    tohost_failure_count = 0
    failure_markers: set[str] = set()
    rvcp_lines: list[str] = []

    try:
        with log_path.open("r", encoding="utf-8", errors="replace") as stream:
            for raw_line in stream:
                line = raw_line.rstrip("\r\n")
                if expected_success.fullmatch(line):
                    expected_success_count += 1
                if _ANY_SUCCESS_RE.fullmatch(line):
                    all_success_count += 1
                if _ANY_TOHOST_FAILURE_RE.fullmatch(line):
                    tohost_failure_count += 1
                for marker in _FAILURE_MARKERS:
                    if marker in line:
                        failure_markers.add(marker)
                if _RVCP_PREFIX in line:
                    rvcp_lines.append(line)
    except OSError as error:
        reasons.append(f"cannot read log: {error}")

    if expected_success_count != 1:
        reasons.append(
            "expected exactly one success marker for the current ELF, "
            f"found {expected_success_count}"
        )
    if all_success_count != 1:
        reasons.append(
            f"expected exactly one total TestHarness success marker, found {all_success_count}"
        )
    if tohost_failure_count:
        reasons.append(f"found {tohost_failure_count} TestHarness failure marker(s)")
    if failure_markers:
        reasons.append("failure marker(s): " + ", ".join(sorted(failure_markers)))

    if rvcp_lines:
        expected_rvcp = (
            'RVCP-SUMMARY: TEST PASSED - Test File "' f'{test.spec.expected_source}"'
        )
        if len(rvcp_lines) != 1:
            reasons.append(
                f"expected exactly one RVCP summary when present, found {len(rvcp_lines)}"
            )
        elif rvcp_lines[0] != expected_rvcp:
            reasons.append(
                "RVCP summary is not the exact PASSED result for the current test"
            )

    if reasons:
        return False, "; ".join(reasons)
    if rvcp_lines:
        return True, "exact TestHarness and RVCP self-check markers matched"
    return True, "exact TestHarness self-check marker matched; RVCP summary absent"


def _terminate_process_group(
    process: subprocess.Popen[bytes], grace_seconds: float = 2.0
) -> None:
    """Terminate the complete session created for one ELF, then force-kill it.

    ``start_new_session=True`` makes the TestHarness PID the process-group ID.
    Keep checking that group even after the leader exits: a simulator child may
    ignore SIGTERM and otherwise survive a successful ``process.wait()`` on the
    leader.
    """

    _validate_positive(grace_seconds, "grace_seconds")
    process_group = process.pid

    def group_exists() -> bool:
        try:
            os.killpg(process_group, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def wait_for_group(deadline: float) -> bool:
        while group_exists():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            # Reap the leader promptly, but group lifetime—not leader lifetime—
            # controls whether cleanup is complete.
            if process.poll() is None:
                try:
                    process.wait(timeout=min(0.05, remaining))
                except subprocess.TimeoutExpired:
                    pass
            else:
                time.sleep(min(0.05, remaining))
        return True

    try:
        os.killpg(process_group, signal.SIGTERM)
    except ProcessLookupError:
        if process.poll() is None:
            try:
                process.wait(timeout=grace_seconds)
            except subprocess.TimeoutExpired:
                pass
        return

    if wait_for_group(time.monotonic() + grace_seconds):
        return

    try:
        os.killpg(process_group, signal.SIGKILL)
    except ProcessLookupError:
        return
    if not wait_for_group(time.monotonic() + grace_seconds):
        raise RunnerError(f"Could not kill TestHarness process group {process_group}")


def _validate_positive(value: int | float, name: str) -> None:
    if isinstance(value, bool) or value <= 0:
        raise RunnerError(f"{name} must be positive")


def _validate_executable(binary: Path) -> Path:
    try:
        metadata = binary.lstat()
    except OSError as error:
        raise RunnerError(
            f"Cannot access TestHarness binary {binary}: {error}"
        ) from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise RunnerError(
            f"TestHarness binary must be a regular non-symlink file: {binary}"
        )
    if not os.access(binary, os.X_OK):
        raise RunnerError(f"TestHarness binary is not executable: {binary}")
    return binary.resolve(strict=True)


def run_test(
    binary: Path,
    test: PreparedTest,
    log_directory: Path,
    *,
    cycle_timeout: int,
    wall_timeout_seconds: float,
    cwd: Path,
    environment: Mapping[str, str] | None = None,
) -> TestResult:
    """Run one ELF with both RTL-cycle and outer wall-clock timeouts."""

    _validate_positive(cycle_timeout, "cycle_timeout")
    _validate_positive(wall_timeout_seconds, "wall_timeout_seconds")
    resolved_binary = _validate_executable(binary)
    resolved_elf = test.path.resolve(strict=True)
    if resolved_elf != test.path:
        raise RunnerError(f"Prepared ELF path is not canonical: {test.path}")

    log_directory.mkdir(parents=True, exist_ok=True)
    if log_directory.is_symlink():
        raise RunnerError(f"Log directory must not be a symlink: {log_directory}")
    log_path = log_directory / f"{test.spec.test_id}.log"
    if os.path.lexists(log_path) and log_path.is_symlink():
        raise RunnerError(f"Refusing to overwrite symlink log: {log_path}")

    command = (
        str(resolved_binary),
        str(resolved_elf),
        f"+elf_file={resolved_elf}",
        f"+time_out={cycle_timeout}",
        "+debug_disable=1",
    )
    runtime_environment = dict(os.environ)
    if environment is not None:
        runtime_environment.update(environment)
    # Never inherit an opt-in live tandem mode from a developer shell.
    runtime_environment.pop("SPIKE_TANDEM", None)

    started = time.monotonic()
    return_code: int | None = None
    timed_out = False
    process: subprocess.Popen[bytes] | None = None
    try:
        with log_path.open("w", encoding="utf-8") as log:
            log.write("ACT4 command: " + " ".join(command) + "\n")
            log.flush()
            try:
                process = subprocess.Popen(
                    list(command),
                    cwd=cwd,
                    env=runtime_environment,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    close_fds=True,
                )
                try:
                    return_code = process.wait(timeout=wall_timeout_seconds)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    _terminate_process_group(process)
                    return_code = process.returncode
            except OSError as error:
                log.write(f"ACT4 runner could not start TestHarness: {error}\n")
                log.flush()
    except KeyboardInterrupt:
        if process is not None:
            _terminate_process_group(process)
        raise
    except OSError as error:
        raise RunnerError(f"Cannot create ACT4 log {log_path}: {error}") from error

    duration = time.monotonic() - started
    passed, detail = evaluate_log(test, log_path, return_code, timed_out)
    return TestResult(
        test_id=test.spec.test_id,
        elf=test.spec.elf,
        passed=passed,
        detail=detail,
        return_code=return_code,
        timed_out=timed_out,
        duration_seconds=duration,
        log_path=log_path,
        command=command,
    )


def run_corpus(
    corpus: PreparedCorpus,
    binary: Path,
    log_directory: Path,
    *,
    cycle_timeout: int,
    wall_timeout_seconds: float,
    cwd: Path,
    environment: Mapping[str, str] | None = None,
) -> tuple[TestResult, ...]:
    """Run every manifest ELF in an isolated cwd and return every result."""

    if not corpus.tests:
        raise RunnerError("Refusing to run a zero-test ACT4 corpus")
    if os.path.lexists(cwd):
        metadata = cwd.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise RunnerError(
                f"ACT4 working root must be a regular non-symlink directory: {cwd}"
            )
    else:
        cwd.mkdir(parents=True, mode=0o755)
    results = []
    for test in corpus.tests:
        test_cwd = cwd / test.spec.test_id
        if os.path.lexists(test_cwd):
            raise RunnerError(
                f"ACT4 per-test working directory already exists: {test_cwd}"
            )
        test_cwd.mkdir(mode=0o755)
        results.append(
            run_test(
                binary,
                test,
                log_directory,
                cycle_timeout=cycle_timeout,
                wall_timeout_seconds=wall_timeout_seconds,
                cwd=test_cwd,
                environment=environment,
            )
        )
    return tuple(results)
