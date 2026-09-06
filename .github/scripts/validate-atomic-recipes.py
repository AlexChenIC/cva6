"""Native validation only; not part of the proposed recipe PRs."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import yaml

out = Path("validation-results")
out.mkdir(exist_ok=True)
target = os.environ["TEST_TARGET"]
trace = os.environ["TEST_TRACE"]
suite = os.environ["TEST_SUITE"]
results = []
paths = ["flows/recipes/verilator_testharness_comp.py", "flows/recipes/verilator_testharness_run.py", "flows/utils/logged_process.py", "verif/tb/core/Flist.verilator_testharness"]
provenance = {
    "head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "target": target, "trace": trace, "suite": suite,
    "source_blobs": {p: subprocess.check_output(["git", "hash-object", p], text=True).strip() for p in paths},
    "submodules": subprocess.check_output(["git", "submodule", "status", "--recursive"], text=True),
}
(out / "provenance.json").write_text(json.dumps(provenance, indent=2))
metadata = Path(os.environ["CONFIG_DIR"]) / "environment.yml"
if metadata.is_file():
    shutil.copy2(metadata, out / "toolchain-environment.yml")


def run(command):
    index = len(results)
    with (out / f"{index:02d}.log").open("w") as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=2400)
    results.append({"command": command, "rc": result.returncode, "log": f"{index:02d}.log"})
    (out / "commands.json").write_text(json.dumps(results, indent=2))
    print(f"rc={result.returncode}: {command}", flush=True)
    if result.returncode:
        print((out / f"{index:02d}.log").read_text()[-12000:])
        raise SystemExit(result.returncode)


cook = [sys.executable, "cook.py"]
run([str(Path(os.environ["VERILATOR_INSTALL_DIR"]) / "bin/verilator"), "--version"])
run(cook + ["verilator-testharness-comp", "--help"])
run(cook + ["verilator-testharness-run", "--help"])
run(cook + ["verilator-testharness-comp", "-t", target, "--trace-mode", trace, "--quiet"])
if suite == "compile":
    raise SystemExit(0)
march = "rv32imc_zicsr_zba_zbb_zbs_zbc" + ("_zifencei" if suite == "pmp" else "")
testlist = "verif/tests/base_pmp.yaml" if suite == "pmp" else "verif/tests/base_rv32_p.yaml"
tests = ["decreasing_entries_test", "exact_csrr_test", "granularity_test", "locked_outside_tor_test", "lsu_tor_test"] if suite == "pmp" else ["rv32ui-p-add"]
command = cook + ["sw-compile-testlist", "-t", target, "-c", "github_actions_gcc", "--testlist", testlist, "--march", march]
if suite != "pmp":
    command += ["--testname", tests[0]]
run(command)
for name in tests:
    name = f"{name}_0"
    for iss in (False, True):
        run(cook + ["verilator-testharness-run", "-t", target, "-n", name, "--trace-mode", trace, "--iss-enabled" if iss else "--no-iss-enabled", "--quiet"])
        simulation = Path("build") / target / "simulation/sim_rtl_verilator_testharness" / name
        result = yaml.safe_load((simulation / "result.yml").read_text())
        assert result["status"] == "PASS" and result["iss_enabled"] == iss, result
        if trace != "notrace":
            extension = "vcd" if trace == "fast" else "fst"
            waveforms = list(simulation.glob(f"*.{extension}"))
            assert waveforms and all(path.stat().st_size > 100 for path in waveforms), waveforms
        shutil.copytree(simulation, out / f"{name}-iss-{iss}", ignore=shutil.ignore_patterns("*.vcd", "*.fst", "*.dasm"))
