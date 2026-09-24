# Copyright 2026 OpenHW Foundation
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from contextlib import contextmanager
import inspect
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml
from typer.testing import CliRunner
from rich.text import Text

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

TEST_CONFIG = tempfile.TemporaryDirectory()
unittest.addModuleCleanup(TEST_CONFIG.cleanup)
CONFIG_PATH = Path(TEST_CONFIG.name)
(CONFIG_PATH / "compiler.yml").write_text(
    "test_toolchain:\n  TOOLS_PATH: /tmp\n  CLANG: null\n  GCC: gcc\n"
    "  OBJDUMP: objdump\n  NM: nm\n  TARGET_TOOLCHAIN: riscv32-unknown-elf\n",
    encoding="utf-8",
)
(CONFIG_PATH / "techno.yml").write_text("{}\n", encoding="utf-8")
os.environ["CONFIG_DIR"] = str(CONFIG_PATH)

from flows.recipes import verilator_testharness_run as RECIPE  # noqa: E402
from flows.utils.manifest import MANIFEST_NAME, write_manifest  # noqa: E402
from flows.utils.utils import CompMode, TraceMode  # noqa: E402


@contextmanager
def working_directory(root: Path):
    previous = Path.cwd()
    os.chdir(root)
    try:
        yield
    finally:
        os.chdir(previous)


def executable(path: Path, body: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!{sys.executable}\n{body}\n", encoding="utf-8")
    path.chmod(0o755)


def prepare_tree(root: Path, trace_mode=TraceMode.notrace):
    target = "cv32a60x_axi"
    name = "hello-world"
    target_dir = root / "config" / "target" / target
    target_dir.mkdir(parents=True)
    for file in ("Flist.cva6", "rtl_cfg_pkg.sv"):
        (target_dir / file).touch()
    (target_dir / "testbench_cfg.yml").write_text("hier: axi\n")
    (target_dir / "isa.yml").write_text("mabi: ilp32\n")
    # No spike.yaml or Spike executable: neither is needed by an RTL-only run.
    compile_dir = root / "build" / target / "compile" / name
    compile_dir.mkdir(parents=True)
    (compile_dir / f"{name}.elf").touch()
    (compile_dir / "isa_string").write_text("rv32imc\n")
    (compile_dir / f"{name}.add_tohost").write_text("80001000\n")
    write_manifest(
        compile_dir, "sw-compile", {"target": target, "test_name": name}, quiet=True
    )
    elab_dir = RECIPE.elaboration_directory(root, target, CompMode.rtl)
    elab_dir.mkdir(parents=True)
    write_manifest(
        elab_dir,
        "verilator-testharness-comp",
        {
            "target": target,
            "comp_mode": "rtl",
            "trace_mode": trace_mode.value,
            "stats": False,
        },
        quiet=True,
    )
    binary = RECIPE.testharness_binary(root, target, CompMode.rtl)
    executable(
        binary,
        "from pathlib import Path\n"
        "Path('trace_rvfi_hart_00.dasm').write_text('diagnostic text\\n')\n"
        "print('*** SUCCESS *** (tohost = 0)')",
    )
    spike = root / "tools" / "spike"
    dasm = spike / "bin" / "spike-dasm"
    executable(
        dasm,
        "import os, sys\n"
        "assert os.environ['TARGET_CFG'] == 'cv32a60x_axi'\n"
        "assert os.environ['SPIKE_INSTALL_DIR']\n"
        "assert os.environ['LD_LIBRARY_PATH']\n"
        "assert 'SPIKE_TANDEM' not in os.environ\n"
        "sys.stdout.write(sys.stdin.read())",
    )
    riscv = root / "tools" / "riscv"
    riscv.mkdir(parents=True)
    env = {"RISCV": str(riscv), "SPIKE_INSTALL_DIR": str(spike), "SPIKE_TANDEM": "1"}
    return compile_dir, elab_dir, binary, dasm, env


def run_options(**overrides):
    return {
        "target": "cv32a60x_axi",
        "test_name": "hello-world",
        "comp_mode": CompMode.rtl,
        "trace_mode": TraceMode.notrace,
        "iss_enabled": False,
        "interactive_gui": False,
        **overrides,
    }


class VerilatorTestHarnessRunTest(unittest.TestCase):
    def test_public_interface_and_default(self):
        parameters = inspect.signature(RECIPE.verilator_testharness_run).parameters
        self.assertEqual(
            list(parameters),
            [
                "target",
                "test_name",
                "comp_mode",
                "trace_mode",
                "iss_enabled",
                "interactive_gui",
                "quiet",
            ],
        )
        self.assertFalse(parameters["iss_enabled"].default.default)

    def test_iss_rejected_before_prerequisites_cleanup_or_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = (
                root
                / "build/cv32a60x_axi/simulation/sim_rtl_verilator_testharness/hello-world"
            )
            output.mkdir(parents=True)
            sentinel = output / "previous-result"
            sentinel.write_text("preserve")
            with working_directory(root), patch.object(
                RECIPE, "target_directory"
            ) as target, patch.object(RECIPE.shutil, "rmtree") as clean, patch.object(
                RECIPE, "run_logged_process"
            ) as execute:
                with self.assertRaisesRegex(
                    ValueError, "ISS comparison is not supported"
                ):
                    RECIPE.run_test(**run_options(iss_enabled=True))
            target.assert_not_called()
            clean.assert_not_called()
            execute.assert_not_called()
            self.assertEqual(sentinel.read_text(), "preserve")

    def test_cli_iss_rejection_is_visible_in_quiet_mode(self):
        with patch.object(RECIPE, "run_logged_process") as execute:
            result = CliRunner().invoke(
                RECIPE.app, ["-t", "absent", "-n", "absent", "--iss-enabled", "--quiet"]
            )
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("ISS comparison is not supported", result.output)
        execute.assert_not_called()

    def test_cook_registers_recipe_and_documents_reserved_iss(self):
        for args in (["--help"], ["verilator-testharness-run", "--help"]):
            with self.subTest(args=args):
                result = subprocess.run(
                    [sys.executable, str(REPO_ROOT / "cook.py"), *args],
                    cwd=REPO_ROOT,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(
                    (
                        "verilator-testharness-run"
                        if len(args) == 1
                        else "not yet supported"
                    ),
                    " ".join(
                        Text.from_ansi(result.stdout)
                        .plain.replace("\u2502", " ")
                        .split()
                    ),
                )

    def test_command_is_direct_and_has_no_iss_configuration(self):
        for mode, flag in (
            (TraceMode.notrace, None),
            (TraceMode.fast, "--vcd"),
            (TraceMode.compact, "--fst"),
        ):
            with self.subTest(mode=mode):
                command = RECIPE.testharness_command(
                    Path("/build/Variane_testharness"),
                    Path("/build/test.elf"),
                    target="cv32a60x_axi",
                    tohost="80001000",
                    trace_mode=mode,
                )
                self.assertEqual(command[0], "/build/Variane_testharness")
                self.assertIn("+tohost_addr=80001000", command)
                if flag:
                    self.assertIn(flag, command)
                else:
                    self.assertNotIn("--vcd", command)
                    self.assertNotIn("--fst", command)
                self.assertFalse(
                    any(
                        "config_file=" in arg
                        or "cva6.py" in arg
                        or "tandem_enabled" in arg
                        for arg in command
                    )
                )

    def test_unsupported_modes_fail(self):
        for options in (
            run_options(interactive_gui=True),
            run_options(comp_mode=CompMode.coverage),
            run_options(trace_mode=TraceMode.gui),
        ):
            with self.subTest(options=options), self.assertRaises(ValueError):
                RECIPE.run_test(**options)

    def test_output_directory_rejects_symlink_and_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "outside").mkdir()
            (root / "build").symlink_to(root / "outside", target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symbolic link"):
                RECIPE.simulation_directory(root, "cv32a60x_axi", "test", CompMode.rtl)
            for name in ("../escape", ".", "..", ""):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    RECIPE.validate_path_component(name, "test")

    def test_simulation_log_success_and_failure_priority(self):
        success = "*** SUCCESS *** (tohost = 0)\n"
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "simulation.log"
            self.assertFalse(RECIPE.testharness_log_passed(log)[0])
            for text, expected in (
                ("", False),
                ("normal exit", False),
                (success, True),
                ("UVM_WARNING\n" + success, True),
                *(
                    (success + marker, False)
                    for marker in (
                        "*** FAILED ***",
                        "SIMULATION FAILED",
                        "[FAILED]",
                        "UVM_ERROR",
                        "UVM_FATAL",
                    )
                ),
            ):
                with self.subTest(text=text):
                    log.write_text(text)
                    self.assertEqual(RECIPE.testharness_log_passed(log)[0], expected)
            log.write_bytes(b"\xff")
            self.assertFalse(RECIPE.testharness_log_passed(log)[0])

    def test_execution_failures_prevent_disassembly(self):
        cases = (
            (7, False, "*** SUCCESS *** (tohost = 0)"),
            (0, True, "*** SUCCESS *** (tohost = 0)"),
            (0, False, "no success"),
            (0, False, "*** SUCCESS *** (tohost = 0)\nUVM_FATAL"),
            (0, False, None),
        )
        for rc, timeout, text in cases:
            with self.subTest(
                rc=rc, timeout=timeout, text=text
            ), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                if text is not None:
                    (root / "testharness.log").write_text(text)
                with patch.object(
                    RECIPE, "run_logged_process", return_value=(rc, timeout)
                ), patch.object(RECIPE, "run_spike_dasm") as dasm:
                    passed, _ = RECIPE.run_testharness_and_trace(
                        command=["fixture"],
                        output_dir=root,
                        env={},
                        spike_install=root,
                        compiler_isa="rv32imc",
                        timeout=1,
                    )
                self.assertFalse(passed)
                dasm.assert_not_called()

    def test_real_subprocess_run_needs_no_spike_executable_or_yaml(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, _, _, env = prepare_tree(root)
            with working_directory(root), patch.dict(os.environ, env):
                passed, detail, output = RECIPE.run_test(**run_options())
            self.assertTrue(passed, detail)
            self.assertEqual(
                (output / "verilator.log").read_text(), "diagnostic text\n"
            )
            self.assertFalse((root / "tools/spike/bin/spike").exists())
            self.assertFalse((root / "config/target/cv32a60x_axi/spike.yaml").exists())
            self.assertFalse((output / "spike.csv").exists())

    def test_real_process_timeout_overrides_early_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, binary, _, env = prepare_tree(root)
            executable(
                binary,
                "import time\n"
                "print('*** SUCCESS *** (tohost = 0)', flush=True)\n"
                "time.sleep(10)",
            )
            with working_directory(root), patch.dict(os.environ, env), patch.object(
                RECIPE, "run_spike_dasm"
            ) as dasm:
                passed, detail, _ = RECIPE.run_test(**run_options(timeout=0.2))
            self.assertFalse(passed)
            self.assertIn("timed out", detail)
            dasm.assert_not_called()

    def test_trace_contents_do_not_gate_execution(self):
        traces = (
            "",
            "not instruction text\n",
            "4 | core 0: 0x90001000 (0x00100093) li ra,1\n",
        )
        for trace in traces:
            with self.subTest(trace=trace), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                _, _, binary, _, env = prepare_tree(root)
                executable(
                    binary,
                    "from pathlib import Path\n"
                    + f"Path('trace_rvfi_hart_00.dasm').write_text({trace!r})\n"
                    + "print('*** SUCCESS *** (tohost = 0)')",
                )
                with working_directory(root), patch.dict(os.environ, env):
                    passed, detail, output = RECIPE.run_test(**run_options())
                self.assertTrue(passed, detail)
                self.assertEqual((output / "verilator.log").read_text(), trace)

    def test_missing_raw_trace_skips_disassembly_and_records_success(self):
        for quiet in (False, True):
            with self.subTest(quiet=quiet), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                _, _, binary, dasm, env = prepare_tree(root)
                executable(binary, "print('*** SUCCESS *** (tohost = 0)')")
                dasm.unlink()
                args = ["-t", "cv32a60x_axi", "-n", "hello-world"]
                if quiet:
                    args.append("--quiet")
                with working_directory(root), patch.dict(os.environ, env), patch.object(
                    RECIPE, "run_spike_dasm"
                ) as disassemble:
                    result = CliRunner().invoke(RECIPE.app, args)
                self.assertEqual(result.exit_code, 0, result.output)
                disassemble.assert_not_called()
                output = RECIPE.simulation_directory(
                    root, "cv32a60x_axi", "hello-world", CompMode.rtl
                )
                record = yaml.safe_load((output / "result.yml").read_text())
                self.assertEqual(record["status"], "PASS")
                self.assertIs(record["iss_enabled"], False)
                self.assertIn("trace disassembly skipped", record["detail"])
                self.assertFalse((output / "verilator.log").exists())
                if not quiet:
                    self.assertIn("trace disassembly skipped", result.output)

    def test_nonregular_trace_paths_are_not_treated_as_missing(self):
        cases = {
            "directory": "raw.mkdir()",
            "dangling-link": "raw.symlink_to('absent')",
            "file-link": "Path('other').touch(); raw.symlink_to('other')",
        }
        if hasattr(os, "mkfifo"):
            cases["fifo"] = "import os; os.mkfifo(raw)"
        for case, setup in cases.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                _, _, binary, _, env = prepare_tree(root)
                executable(
                    binary,
                    "from pathlib import Path\n"
                    "raw = Path('trace_rvfi_hart_00.dasm')\n"
                    + setup
                    + "\nprint('*** SUCCESS *** (tohost = 0)')",
                )
                with working_directory(root), patch.dict(os.environ, env), patch.object(
                    RECIPE, "run_spike_dasm"
                ) as disassemble:
                    passed, detail, _ = RECIPE.run_test(**run_options())
                self.assertFalse(passed)
                self.assertIn(
                    "RTL simulation passed; trace post-processing failed", detail
                )
                self.assertIn("not a regular file", detail)
                disassemble.assert_not_called()

    def test_trace_inspection_error_is_not_treated_as_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, _, _, env = prepare_tree(root)
            original = Path.lstat

            def denied(path, *args, **kwargs):
                if path.name == "trace_rvfi_hart_00.dasm":
                    raise PermissionError("trace metadata denied")
                return original(path, *args, **kwargs)

            with working_directory(root), patch.dict(os.environ, env), patch.object(
                Path, "lstat", denied
            ), patch.object(RECIPE, "run_spike_dasm") as disassemble:
                passed, detail, _ = RECIPE.run_test(**run_options())
            self.assertFalse(passed)
            self.assertIn("cannot inspect raw trace: trace metadata denied", detail)
            disassemble.assert_not_called()

    def test_trace_io_errors_after_inspection_are_not_skipped(self):
        cases = (
            ("trace_rvfi_hart_00.dasm", PermissionError),
            ("trace_rvfi_hart_00.dasm", FileNotFoundError),
            ("verilator.log", PermissionError),
            ("spike_dasm.log", PermissionError),
        )
        for name, error in cases:
            with self.subTest(
                name=name, error=error
            ), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                _, _, _, _, env = prepare_tree(root)
                original = Path.open

                def denied(path, *args, **kwargs):
                    if path.name == name:
                        raise error("fixture I/O denied")
                    return original(path, *args, **kwargs)

                with working_directory(root), patch.dict(os.environ, env), patch.object(
                    Path, "open", denied
                ):
                    passed, detail, _ = RECIPE.run_test(**run_options())
                self.assertFalse(passed)
                self.assertIn(
                    "RTL simulation passed; trace post-processing failed", detail
                )
                self.assertIn("fixture I/O denied", detail)

    def test_disassembler_nonzero_and_missing_tool_fail(self):
        for case in ("exit-7", "missing", "non-executable", "directory"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                _, _, _, dasm, env = prepare_tree(root)
                if case == "missing":
                    dasm.unlink()
                elif case == "non-executable":
                    dasm.chmod(0o644)
                elif case == "directory":
                    dasm.unlink()
                    dasm.mkdir()
                else:
                    executable(dasm, "raise SystemExit(7)")
                with working_directory(root), patch.dict(os.environ, env):
                    result = CliRunner().invoke(
                        RECIPE.app,
                        ["-t", "cv32a60x_axi", "-n", "hello-world", "--quiet"],
                    )
                self.assertEqual(result.exit_code, 1, result.output)
                output = RECIPE.simulation_directory(
                    root, "cv32a60x_axi", "hello-world", CompMode.rtl
                )
                record = yaml.safe_load((output / "result.yml").read_text())
                self.assertEqual(record["status"], "FAIL")
                self.assertIn(
                    "RTL simulation passed; trace post-processing failed",
                    record["detail"],
                )
                if case == "exit-7":
                    self.assertIn("spike-dasm exited with code 7", record["detail"])
                else:
                    self.assertIn("I/O or launch error", record["detail"])
                    self.assertIn(str(dasm), record["detail"])

    def test_disassembler_timeout_and_write_error_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "raw"
            raw.touch()
            dasm = root / "dasm"
            dasm.touch()
            args = (dasm, raw, root / "out", root / "err", "rv32imc", 1)
            with patch.object(
                RECIPE.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired("dasm", 1),
            ):
                passed, detail = RECIPE.run_spike_dasm(*args, env={})
                self.assertFalse(passed)
                self.assertIn("spike-dasm timed out after 1 seconds", detail)
            with patch.object(Path, "open", side_effect=PermissionError("fixture")):
                passed, detail = RECIPE.run_spike_dasm(*args, env={})
                self.assertFalse(passed)
                self.assertIn("I/O or launch error: fixture", detail)

    def test_real_disassembler_timeout_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "raw"
            raw.touch()
            dasm = root / "dasm"
            executable(dasm, "import time; time.sleep(10)")
            passed, detail = RECIPE.run_spike_dasm(
                dasm,
                raw,
                root / "out",
                root / "err",
                "rv32imc",
                0.2,
                env=os.environ.copy(),
            )
            self.assertFalse(passed)
            self.assertIn("spike-dasm timed out", detail)

    def test_disassembler_receives_prepared_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "testharness.log").write_text("*** SUCCESS *** (tohost = 0)")
            (root / "trace_rvfi_hart_00.dasm").touch()
            env = {"TARGET_CFG": "expected"}
            with patch.object(
                RECIPE, "run_logged_process", return_value=(0, False)
            ), patch.object(
                RECIPE,
                "run_spike_dasm",
                return_value=(True, "trace disassembly completed"),
            ) as dasm:
                passed, _ = RECIPE.run_testharness_and_trace(
                    command=["fixture"],
                    output_dir=root,
                    env=env,
                    spike_install=root,
                    compiler_isa="rv32imc",
                    timeout=1,
                )
            self.assertTrue(passed)
            self.assertIs(dasm.call_args.kwargs["env"], env)

    def test_invalid_inputs_do_not_delete_previous_results(self):
        cases = (
            "missing-elf",
            "empty-isa",
            "zero-tohost",
            "non-executable",
            "wrong-target",
            "wrong-recipe",
            "missing-manifest",
            "malformed-manifest",
            "wrong-trace",
        )
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                compile_dir, elab_dir, binary, _, env = prepare_tree(root)
                options = run_options()
                if case == "missing-elf":
                    (compile_dir / "hello-world.elf").unlink()
                elif case == "empty-isa":
                    (compile_dir / "isa_string").write_text("")
                elif case == "zero-tohost":
                    (compile_dir / "hello-world.add_tohost").write_text("0")
                elif case == "non-executable":
                    binary.chmod(0o644)
                elif case in {"wrong-target", "wrong-recipe"}:
                    file = elab_dir / MANIFEST_NAME
                    data = yaml.safe_load(file.read_text())
                    if case == "wrong-target":
                        data["options"]["target"] = "other"
                    else:
                        data["recipe"] = "vcs-uvm-comp"
                    file.write_text(yaml.safe_dump(data))
                elif case == "missing-manifest":
                    (compile_dir / MANIFEST_NAME).unlink()
                elif case == "malformed-manifest":
                    (elab_dir / MANIFEST_NAME).write_text("[]")
                else:
                    options["trace_mode"] = TraceMode.fast
                output = RECIPE.simulation_directory(
                    root, options["target"], options["test_name"], CompMode.rtl
                )
                output.mkdir(parents=True)
                (output / "previous").write_text("preserve")
                with working_directory(root), patch.dict(os.environ, env), patch.object(
                    RECIPE, "run_logged_process"
                ) as execute:
                    with self.assertRaises((ValueError, SystemExit, RECIPE.typer.Exit)):
                        RECIPE.run_test(**options)
                execute.assert_not_called()
                self.assertEqual((output / "previous").read_text(), "preserve")

    def test_cli_records_actual_rtl_only_result_and_manifest(self):
        for fail in (False, True):
            with self.subTest(fail=fail), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                _, _, binary, _, env = prepare_tree(root)
                if fail:
                    executable(
                        binary,
                        "print('*** SUCCESS *** (tohost = 0)')\nraise SystemExit(7)",
                    )
                with working_directory(root), patch.dict(os.environ, env):
                    result = CliRunner().invoke(
                        RECIPE.app,
                        ["-t", "cv32a60x_axi", "-n", "hello-world", "--quiet"],
                    )
                self.assertEqual(result.exit_code, 1 if fail else 0, result.output)
                output = RECIPE.simulation_directory(
                    root, "cv32a60x_axi", "hello-world", CompMode.rtl
                )
                record = yaml.safe_load((output / "result.yml").read_text())
                manifest = yaml.safe_load((output / MANIFEST_NAME).read_text())
                self.assertEqual(record["status"], "FAIL" if fail else "PASS")
                self.assertIs(record["iss_enabled"], False)
                self.assertIs(manifest["options"]["iss_enabled"], False)
                if fail:
                    self.assertIn("returned 7", result.output)

    def test_cli_fails_when_manifest_writing_is_swallowed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, _, _, env = prepare_tree(root)
            with working_directory(root), patch.dict(os.environ, env), patch.object(
                RECIPE, "write_manifest"
            ):
                result = CliRunner().invoke(
                    RECIPE.app, ["-t", "cv32a60x_axi", "-n", "hello-world"]
                )
            self.assertNotEqual(result.exit_code, 0)
            self.assertIn("manifest was not written correctly", result.output)

    def test_rerun_replaces_previous_pass_with_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, binary, _, env = prepare_tree(root)
            args = ["-t", "cv32a60x_axi", "-n", "hello-world", "--quiet"]
            with working_directory(root), patch.dict(os.environ, env):
                first = CliRunner().invoke(RECIPE.app, args)
                self.assertEqual(first.exit_code, 0, first.output)
                executable(binary, "raise SystemExit(7)")
                second = CliRunner().invoke(RECIPE.app, args)
            self.assertEqual(second.exit_code, 1, second.output)
            output = RECIPE.simulation_directory(
                root, "cv32a60x_axi", "hello-world", CompMode.rtl
            )
            self.assertEqual(
                yaml.safe_load((output / "result.yml").read_text())["status"], "FAIL"
            )
            self.assertFalse((output / "verilator.log").exists())
            self.assertFalse((output / "trace_rvfi_hart_00.dasm").exists())

    def test_cli_fails_when_result_cannot_be_written(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, _, _, env = prepare_tree(root)
            original = Path.write_text

            def fail_result(path, *args, **kwargs):
                if path.name == "result.yml":
                    raise OSError("result write denied")
                return original(path, *args, **kwargs)

            with working_directory(root), patch.dict(os.environ, env), patch.object(
                Path, "write_text", fail_result
            ):
                result = CliRunner().invoke(
                    RECIPE.app, ["-t", "cv32a60x_axi", "-n", "hello-world"]
                )
            self.assertNotEqual(result.exit_code, 0)
            self.assertIn("Cannot write run result", result.output)


if __name__ == "__main__":
    unittest.main()
