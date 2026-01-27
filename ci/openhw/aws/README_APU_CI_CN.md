# CVA6 APU CI 变更说明与使用指南（本次改动）

本文档记录了我在 `ci/openhw/aws` 体系内做的修改、当前可实现的能力、尚未覆盖的内容，以及本地/CI/AWS self-hosted 的测试方法与后续建议。

## 1. 本次修改清单（按文件）

**新增/更新的文件**
- `ci/openhw/aws/env_setup.sh`
  - 允许外部覆盖 `RISCV/VERILATOR/SPIKE` 路径。
  - 补齐 `QUESTA_HOME` 与 `QUESTASIM_HOME` 关系。
- `ci/openhw/aws/build_infrastructure.sh`
  - 增加可跳过 apt / toolchain / verilator / spike / pip 的开关（`CVA6_CI_SKIP_*`）。
- `ci/openhw/aws/run_verification.sh`
  - 统一模拟器映射（`verilator / questa-testharness / questa-uvm / vcs-*`）。
  - 添加 Questa 预检（`vsim`、`QUESTASIM_HOME`、UVM 目录、license 变量）。
- `ci/openhw/aws/run_test_suite.sh`
  - 新增 suite：`issue`, `smoke-gen`, `csr-embedded`, `interrupt`。
  - 增加兼容性约束：UVM suite 仅允许 `questa-uvm`/`vcs-uvm`；
    `pmp/smoke-gen/csr-embedded/interrupt` 仅支持 `cv32a65x`；
    `mmu` 仅支持 `cv32a6_imac_sv32`。
- `ci/openhw/aws/README_CN.md`
  - 补充 Questa workflow 说明与新增 suite 说明。
- `.github/workflows/verilator-apu-ci.yml`
  - 在 Verilator 矩阵里增加 `compliance`。
- `.github/workflows/questa-apu-ci.yml`（新增）
  - 新增 self-hosted 的 Questa testharness 与 UVM workflow（默认 `workflow_dispatch`）。

**未修改（官方文件）**
- `verif/regress/*.sh`、`ci/*.sh`、`.github/workflows/ci.yml` 均未动。

## 2. 现在能实现什么

**Verilator（GitHub-hosted 或本地）**
- `cv32a65x` / `cv64a6_imafdc_sv39` 组合
- 套件：`smoke`, `arch`, `compliance`, `benchmarks`
- 入口统一为 `ci/openhw/aws/run_test_suite.sh` → `ci/openhw/aws/run_verification.sh`

**Questa testharness（self-hosted）**
- `cv32a65x` / `cv64a6_imafdc_sv39`
- 套件：`smoke`, `arch`, `compliance`, `benchmarks`

**Questa UVM（self-hosted）**
- 仅 `cv32a65x`
- 套件：`pmp`, `smoke-gen`, `csr-embedded`, `interrupt`

## 3. 尚未实现或受限的部分

- `dv-generated-tests.sh`、`dv-generated-xif-tests.sh` 硬编码 `--iss=vcs-uvm,spike`，无法直接切到 Questa。
- `debug_test.sh`、`coremark.sh`、`dhrystone.sh` 默认 `vcs-uvm`，需要 UVM 许可与环境支持。
- `cvxif_verif_regression.sh` 里有 `--iss=vcs-uvm` 硬编码（cv32a65x 分支）。
- `issue-tests.sh` 里目标配置是脚本内部固定的 `cv64a6_imafdc_sv39` / `cv32a6_imafc_sv32`，忽略传入 target。
- 文档提到 `cv32a65x` 的 Verilator tandem 需要 Verilator ≥5.016；当前安装脚本是 5.008（潜在风险，未调整）。
- 未实现 VCS/DSim 的 workflow，仅提供 Questa self-hosted。

## 4. 本地测试方法

### 4.1 本地 Verilator（立刻可跑）

**准备环境**
```bash
./ci/openhw/aws/build_infrastructure.sh
```

**推荐用例（快速验证）**
```bash
./ci/openhw/aws/run_test_suite.sh smoke cv32a65x verilator
./ci/openhw/aws/run_test_suite.sh arch cv64a6_imafdc_sv39 verilator
./ci/openhw/aws/run_test_suite.sh compliance cv64a6_imafdc_sv39 verilator
./ci/openhw/aws/run_test_suite.sh benchmarks cv32a65x verilator
```

**如果你已经预装工具链/Spike/Verilator**
```bash
export CVA6_CI_SKIP_APT=1
export CVA6_CI_SKIP_TOOLCHAIN=1
export CVA6_CI_SKIP_SPIKE=1
export CVA6_CI_SKIP_VERILATOR=1
./ci/openhw/aws/build_infrastructure.sh
```

### 4.2 本地 Questa Testharness（有安装时）

**必要环境变量**
```bash
export QUESTASIM_HOME=/opt/siemens/questasim
export LM_LICENSE_FILE=27000@license-server
export CVA6_CI_REQUIRE_LICENSE=1
```

**运行**
```bash
./ci/openhw/aws/run_test_suite.sh smoke cv32a65x questa-testharness
./ci/openhw/aws/run_test_suite.sh arch cv64a6_imafdc_sv39 questa-testharness
```

### 4.3 本地 Questa UVM（有安装时）

**必要环境变量**
```bash
export QUESTASIM_HOME=/opt/siemens/questasim
export LM_LICENSE_FILE=27000@license-server
export CVA6_CI_REQUIRE_LICENSE=1
```

**运行（仅 cv32a65x）**
```bash
./ci/openhw/aws/run_test_suite.sh pmp cv32a65x questa-uvm
./ci/openhw/aws/run_test_suite.sh csr-embedded cv32a65x questa-uvm
./ci/openhw/aws/run_test_suite.sh interrupt cv32a65x questa-uvm
```

## 5. GitHub Actions 上如何测试

### 5.1 Verilator CI
- Workflow：`verilator-apu-ci.yml`
- 触发：push/PR 到 `master/main` 或手动触发
- 矩阵：
  - target：`cv32a65x`, `cv64a6_imafdc_sv39`
  - suite：`smoke`, `arch`, `compliance`, `benchmarks`

**手动触发**
1. GitHub → Actions → Verilator APU CI
2. 点击 “Run workflow”

### 5.2 Questa CI（self-hosted）
- Workflow：`questa-apu-ci.yml`
- 触发：仅 `workflow_dispatch`
- 需要自托管 runner 标签：`self-hosted, linux, questa`

**仓库变量/密钥**
- `vars.QUESTASIM_HOME` / `vars.QUESTA_HOME`
- `secrets.LM_LICENSE_FILE` 或 `secrets.SALT_LICENSE_SERVER` 或 `secrets.MGLS_LICENSE_FILE`

**手动触发**
1. GitHub → Actions → Questa APU CI (Self-hosted)
2. 点击 “Run workflow”

## 6. AWS self-hosted 可用后的操作建议

### 6.1 不改代码即可启用的部分
- 部署 self-hosted runner，标签设置为 `self-hosted, linux, questa`
- 预装 Questa + 许可证环境
- 设置 GitHub 仓库变量/密钥：
  - `QUESTASIM_HOME`、`QUESTA_HOME`
  - `LM_LICENSE_FILE` / `SALT_LICENSE_SERVER` / `MGLS_LICENSE_FILE`
- 直接触发 `questa-apu-ci.yml`

### 6.2 如果要调整行为（可选）
- **runner 已预装全部工具**：
  - 将 `questa-apu-ci.yml` 中 `CVA6_CI_SKIP_TOOLCHAIN=1`、`CVA6_CI_SKIP_SPIKE=1` 打开。
- **希望 self-hosted 也跑 Verilator**：
  - 将 `verilator-apu-ci.yml` 的 `runs-on` 改为自托管标签，或新增一个 self-hosted 版本的 workflow。
- **license 并发不足**：
  - 调小 `max-parallel` 或按许可证数量设置 `concurrency`。

### 6.3 AWS 自托管测试步骤
```bash
# runner 内执行（或通过 workflow 调用）
./ci/openhw/aws/build_infrastructure.sh
./ci/openhw/aws/run_test_suite.sh smoke cv32a65x questa-testharness
./ci/openhw/aws/run_test_suite.sh pmp cv32a65x questa-uvm
```

## 7. 已知风险与建议

- Verilator 版本要求与文档不一致（tandem 5.016+）；如遇 `cv32a65x` tandem 异常，建议升级 Verilator。
- 部分 suite 仍 VCS 固定（generated/cvxif/debug），需新增 wrapper 或等待官方脚本支持 Questa。
- `issue` 套件内部 target 固定，建议仅用于脚本默认目标。

## 8. 你下一步如果要我做什么

1. 增加 `cvxif`/`generated` 的 Questa wrapper（不改官方脚本）。
2. 将 Verilator 版本升级到 5.016+ 并评估影响。
3. 增加 self-hosted Verilator workflow（便于 AWS 上快速回归）。
