# CVA6 CI 系统现状清单 (Current CI Inventory)

**文档目的**：详细列出 CVA6 仓库中现有的所有 CI/Regression 相关文件、配置、测试和工具

**更新日期**：2026-01-17

**基于代码版本**：master 分支 (commit: 59f73d27)

---

## 一、CI 配置文件清单

### 1.1 GitLab CI 配置

#### **主配置文件**
- **路径**：`.gitlab-ci.yml`（24,287 字节）
- **作用**：GitLab CI 的主流程定义
- **维护者**：Thales Silicon Security
- **特点**：
  - 使用 remote include（从 `setup-ci` 仓库引入配置）
  - 支持自定义覆盖（`.gitlab-ci-custom.yml`）
  - 动态触发规则（根据分支类型调整测试范围）

#### **触发规则（Workflow Rules）**

| 触发条件 | CI_KIND | 说明 |
|---------|---------|------|
| `$CI_PIPELINE_SOURCE == "schedule"` | `verif` | 定时任务（weekly）|
| `$CI_COMMIT_BRANCH == "master"` | `regress` | Master 分支 |
| `$CI_PIPELINE_SOURCE == "merge_request_event"` | `regress` | Merge Request |
| `$CI_COMMIT_BRANCH =~ /.*_PR_.*/ 或 /^dev.*/` | `dev` | 开发分支 |
| 其他 | `none` | 无 CI |

#### **Stages（6 个阶段）**

1. **setup** - 环境检查和工具构建
   - `check_env`: 打印环境变量
   - `build_tools`: 构建 Spike ISS

2. **light tests** - 快速冒烟测试（10-30 分钟）
   - `smoke-tests`: Verilator + VCS smoke test（多配置并行）
   - `smoke-gen`: CVA6-DV 生成测试
   - `smoke-bench`: 性能基准测试
   - `smoke-hwconfig`: 硬件配置测试
   - `hello-pk`: Proxy Kernel 测试

3. **heavy tests** - 长时间回归测试（2-6 小时）
   - `it-test`: 指令追踪测试
   - `spyglass`: Lint 检查
   - `cvxif-regression`: CVXIF 接口回归
   - `asic-synthesis`: ASIC 综合
   - `fpga-build`: FPGA 构建
   - `pmp_tests`: 物理内存保护测试
   - `benchmarks`: 性能基准
   - `riscv_arch_test`: RISC-V 架构测试
   - `compliance`: 合规性测试
   - `riscv-tests-v/p`: RISC-V 官方测试
   - `mmu_sv32_tests`: MMU SV32 测试
   - `generated_tests`: 随机生成测试（6 个并行 job）
   - `directed_isacov-tests`: 定向 ISA 覆盖率测试
   - `csr_embedded_tests`: CSR 嵌入式测试

4. **backend tests** - 后端验证
   - `simu-gate`: 门级仿真 + 功耗分析
   - `fpga-boot`: FPGA Linux 启动测试
   - `code_coverage-report`: 代码覆盖率报告合并

5. **find failures** - 失败检测
   - `check gitlab jobs status`: 环境问题检测

6. **report** - 报告合并
   - `merge reports`: 合并所有 job 报告为单一 YAML

#### **关键变量**

```yaml
GIT_SUBMODULE_STRATEGY: recursive
DASHBOARD: cva6
DV_TARGET: cv32a65x  # 默认目标
```

#### **需要用户定义的变量**（GitLab Settings > CI/CD > Variables）

| 变量名 | 用途 | 示例值 |
|--------|------|--------|
| `SETUP_CI_CVV_BRANCH` | CVA6 主分支名 | `master` |
| `TAGS_RUNNER` | 通用 runner 标签 | `cva6-runner` |
| `TAGS_RUNNER_SIMU` | 仿真 runner 标签 | `cva6-sim` |
| `TAGS_RUNNER_SYNTH` | 综合 runner 标签 | `cva6-synth` |
| `TAGS_RUNNER_FPGA` | FPGA runner 标签 | `cva6-fpga` |
| `SYN_VCS_BASHRC` | VCS 环境脚本路径 | `/tools/synopsys/vcs.bashrc` |
| `QUESTA_BASHRC` | Questa 环境脚本 | `/tools/mentor/questa.bashrc` |
| `SYN_SG_BASHRC` | Spyglass 环境脚本 | `/tools/synopsys/sg.bashrc` |
| `SYN_DCSHELL_BASHRC` | DC Shell 环境脚本 | `/tools/synopsys/dc.bashrc` |
| `VIVADO_SETUP` | Vivado 环境脚本 | `/tools/xilinx/vivado.sh` |
| `DASHBOARD_URL` | Dashboard Git 仓库 URL | `git@gitlab:dashboard.git` |
| `DASHBOARD_USER_EMAIL` | Dashboard 提交邮箱 | `ci@example.com` |
| `DASHBOARD_USER_NAME` | Dashboard 提交用户名 | `CVA6 CI Bot` |

### 1.2 GitHub Actions 配置

#### **Workflow 文件清单**

| 文件路径 | 作用 | 触发条件 |
|---------|------|---------|
| `.github/workflows/ci.yml` | 主 CI 流程 | push, pull_request |
| `.github/workflows/bender-up-to-date.yml` | Bender 依赖检查 | push, PR, manual |
| `.github/workflows/verible.yml` | SystemVerilog 格式检查 | pull_request_target |
| `.github/workflows/stale.yml` | 关闭过期 issue/PR | 每日定时 (cron: '30 1 * * *') |
| `.github/workflows/dashboard-done.yml` | GitLab CI 完成通知 | workflow_dispatch |

#### **主 CI Workflow 详解**（`.github/workflows/ci.yml`）

**Jobs 结构**：

1. **build-riscv-tests**
   - 运行环境：`ubuntu-latest`
   - 并行数：`NUM_JOBS=8`
   - 缓存策略：
     - toolchain（key: `hashFiles('ci/install-toolchain.sh')`）
     - verilator（key: `hashFiles('verif/regress/install-verilator.sh')`）
     - spike（key: `hashFiles('verif/regress/install-spike.sh') + submodule-hash`）
   - 执行步骤：
     ```bash
     ci/setup.sh  # 安装所有工具
     ```

2. **execute-riscv64-tests**
   - 依赖：`build-riscv-tests`
   - 矩阵：
     - testcase: `cv64a6_imafdc_tests`, `dv-riscv-arch-test`
     - config: `cv64a6_imafdc_sv39_hpdcache`, `cv64a6_imafdc_sv39_hpdcache_wb`, `cv64a6_imafdc_sv39_wb`, `cv64a6_imafdc_sv39`
     - simulator: `veri-testharness`
   - 环境变量：
     - `SPIKE_TANDEM=1`
   - 执行命令：
     ```bash
     DV_SIMULATORS=${{matrix.simulator}},spike \
     DV_TARGET=${{matrix.config}} \
     bash verif/regress/${{matrix.testcase}}.sh
     ```
   - Artifacts：上传 `verif/sim/out*` 到 GitHub

3. **execute-riscv32-tests**
   - 矩阵：
     - testcase: `dv-riscv-arch-test`, `cv32a6_tests`
     - config: `cv32a65x`
     - simulator: `veri-testharness`
   - 其他配置与 riscv64-tests 相同

#### **总测试任务数**（GitHub Actions）

- RV64 测试：4 configs × 1 testcase + 2 arch-test = **6 jobs**
- RV32 测试：1 config × 2 testcases = **2 jobs**
- **总计**：8 个并行 job

#### **运行时间估算**（使用 cache）

- 第一次运行：~40 分钟（需构建工具）
- 后续运行（cache 命中）：~30 分钟

---

## 二、CI 脚本清单

### 2.1 ci/ 目录（GitHub Actions 安装脚本）

| 文件名 | 作用 | 被谁调用 |
|-------|------|---------|
| `ci/setup.sh` | GitHub Actions 主安装脚本 | `.github/workflows/ci.yml` |
| `ci/make-tmp.sh` | 创建 tmp 目录 | `setup.sh` |
| `ci/install-prereq.sh` | 安装系统依赖 | `setup.sh` |
| `ci/install-toolchain.sh` | 下载 RISC-V toolchain | `setup.sh` |
| `ci/build-riscv-tests.sh` | 构建 riscv-tests | 手动 |
| `ci/build-riscv-gcc.sh` | 构建 GCC（已废弃，使用预编译版本）| - |
| `ci/check-tests.sh` | 检查测试结果 | 回归脚本 |
| `ci/path-setup.sh` | 设置 PATH 变量 | - |
| `ci/default.config` | Torture 配置 | - |
| `ci/float.config` | Torture 浮点配置 | - |
| `ci/riscv-amo-tests.list` | AMO 测试列表 | - |
| `ci/riscv-benchmarks.list` | 基准测试列表 | - |
| `ci/riscv-asm-tests.list` | ASM 测试列表 | - |
| `ci/riscv-mul-tests.list` | 乘法测试列表 | - |
| `ci/riscv-fp-tests.list` | 浮点测试列表 | - |

### 2.2 verif/regress/ 目录（回归测试脚本）

#### **工具安装脚本**

| 文件名 | 安装内容 | 版本/来源 | 安装路径 |
|-------|---------|----------|---------|
| `install-verilator.sh` | Verilator | v5.008 + patch | `tools/verilator/` |
| `install-spike.sh` | Spike ISS | vendorized (core-v-verif) | `tools/spike/` |
| `install-pk.sh` | Proxy Kernel | 官方仓库 | `tools/pk/` |
| `install-riscv-tests.sh` | RISC-V ISA 测试 | 官方仓库 + 补丁 | `tmp/riscv-tests/` |
| `install-riscv-arch-test.sh` | RISC-V 架构测试 | hash: a5a49fc9 | `tmp/riscv-arch-test/` |
| `install-riscv-compliance.sh` | 合规性测试（旧版）| 官方仓库 | `tmp/riscv-compliance/` |

#### **Smoke Tests（快速验证）**

| 文件名 | 目标配置 | 测试数量 | 运行时间 |
|-------|---------|---------|---------|
| `smoke-tests-cv64a6_imafdc_sv39.sh` | cv64a6_imafdc_sv39 | ~10 | 5-10 min |
| `smoke-tests-cv32a65x.sh` | cv32a65x | ~10 | 5-10 min |
| `smoke-tests-cv32a6_imac_sv32.sh` | cv32a6_imac_sv32 | ~10 | 5-10 min |
| `smoke-gen_tests.sh` | 可配置 | ~5 | 10 min |

**smoke-tests 内容示例**（cv64a6_imafdc_sv39）：
```bash
# 安装工具
source ./verif/regress/install-verilator.sh
source ./verif/regress/install-spike.sh

# 安装测试套件
source ./verif/regress/install-riscv-compliance.sh
source ./verif/regress/install-riscv-tests.sh
source ./verif/regress/install-riscv-arch-test.sh

# 运行测试
python3 cva6.py --testlist=../tests/testlist_riscv-compliance-cv64a6_imafdc_sv39.yaml \
                --test rv32i-I-ADD-01 \
                --iss_yaml cva6.yaml \
                --target cv64a6_imafdc_sv39 \
                --iss=$DV_SIMULATORS $DV_OPTS

python3 cva6.py --testlist=../tests/testlist_riscv-tests-cv64a6_imafdc_sv39-v.yaml \
                --test rv64ui-v-add \
                --iss_yaml cva6.yaml \
                --target cv64a6_imafdc_sv39 \
                --iss=$DV_SIMULATORS $DV_OPTS
```

#### **完整测试套件**

| 文件名 | 测试类型 | 测试数量 | 运行时间 |
|-------|---------|---------|---------|
| `cv64a6_imafdc_tests.sh` | RV64 ISA 测试 | ~350 | 2-4 h |
| `cv32a6_tests.sh` | RV32 ISA 测试 | ~250 | 1-2 h |
| `dv-riscv-arch-test.sh` | 架构合规性 | ~200 | 1-2 h |
| `dv-riscv-tests.sh` | 官方 ISA 测试 | ~350 | 2-4 h |
| `dv-riscv-compliance.sh` | 旧版合规性 | ~150 | 1-2 h |
| `dv-generated-tests.sh` | 随机生成测试 | 100-1000 iter | 2-6 h |
| `dv-generated-xif-tests.sh` | CVXIF 随机测试 | 可配置 | 1-2 h |
| `dv-riscv-mmu-sv32-test.sh` | MMU SV32 测试 | ~50 | 6 h |

#### **专项测试**

| 文件名 | 测试内容 | 运行时间 |
|-------|---------|---------|
| `debug_test.sh` | Debug 模块 | 30 min |
| `dv-interrupt-test.sh` | 中断处理 | 30 min |
| `pmp_cv32a65x_tests.sh` | PMP（物理内存保护）| 1 h |
| `hwconfig_tests.sh` | 硬件配置测试 | 30 min |
| `Instr_tracing_test.sh` | 指令追踪 | 2 h |
| `cvxif_verif_regression.sh` | CVXIF 验证回归 | 1 h |
| `iti_test.sh` | ITI 测试 | 30 min |
| `issue-tests.sh` | Bug 修复验证 | 1 h |
| `iss-tests.sh` | ISS 对比测试 | 2 h |
| `veri-testharness-pk-tests.sh` | Proxy Kernel 测试 | 30 min |

#### **性能基准测试**

| 文件名 | 基准程序 | 运行时间 |
|-------|---------|---------|
| `benchmark.sh` | 综合基准 | 1 h |
| `coremark.sh` | CoreMark | 30 min |
| `dhrystone.sh` | Dhrystone | 20 min |
| `dhrystone_smoke.sh` | Dhrystone（快速）| 5 min |
| `linux.sh` | Linux 启动 | 10 min |

### 2.3 .gitlab-ci/scripts/ 目录（报告生成脚本）

| 文件名 | 输入 | 输出 | 用途 |
|-------|-----|------|------|
| `report_builder.py` | - | - | 报告框架基类 |
| `report_simu.py` | `logfile.log` | YAML | 解析仿真测试结果 |
| `report_tandem.py` | Spike tandem 日志 | YAML | Tandem 验证结果 |
| `report_coverage.py` | URG 报告 | YAML | 代码+功能覆盖率 |
| `report_synth.py` | 综合报告 | YAML | 面积、时序 |
| `report_spyglass_lint.py` | Spyglass 日志 | YAML | Lint 错误/警告 |
| `report_benchmark.py` | 基准日志 | YAML | 性能数据 |
| `report_fpga.py` | Vivado 报告 | YAML | FPGA 资源利用率 |
| `report_fpga_boot.py` | 启动日志 | YAML | Linux 启动状态 |
| `merge_job_reports.py` | `artifacts/reports/*.yml` | `pipeline_report_*.yml` | 合并所有报告 |
| `github_integration.py` | Pipeline 状态 | GitHub PR 评论 | 集成到 GitHub |
| `report_fail.py` | - | YAML | 失败占位符 |
| `report_pass.py` | - | YAML | 成功占位符 |
| `report_envfail.py` | - | YAML | 环境失败 |

---

## 三、测试用例和 Testlist 清单

### 3.1 Testlist 文件组织

**位置**：`verif/tests/testlist_*.yaml`

**总数**：28 个 testlist 文件

#### **按测试来源分类**

**A. riscv-tests（官方 ISA 测试）**

| Testlist 文件 | 目标配置 | 模式 | 测试数量 |
|--------------|---------|------|---------|
| `testlist_riscv-tests-cv64a6_imafdc_sv39-p.yaml` | cv64a6_imafdc_sv39 | Physical | ~350 |
| `testlist_riscv-tests-cv64a6_imafdc_sv39-v.yaml` | cv64a6_imafdc_sv39 | Virtual | ~350 |
| `testlist_riscv-tests-cv32a60x-v.yaml` | cv32a60x | Virtual | ~250 |
| `testlist_riscv-tests-cv32a65x-v.yaml` | cv32a65x | Virtual | ~250 |
| `testlist_riscv-tests-cv32a6_imac_sv0-v.yaml` | cv32a6_imac_sv0 | Virtual | ~200 |
| `testlist_riscv-tests-rv32ima-p.yaml` | rv32ima | Physical | ~250 |
| `testlist_riscv-tests-rv32ima-v.yaml` | rv32ima | Virtual | ~250 |

**B. riscv-compliance / riscv-arch-test**

| Testlist 文件 | 目标配置 | 测试数量 |
|--------------|---------|---------|
| `testlist_riscv-compliance-cv64a6_imafdc_sv39.yaml` | cv64a6_imafdc_sv39 | ~150 |
| `testlist_riscv-compliance-rv32ima.yaml` | rv32ima | ~120 |
| `testlist_riscv-arch-test-cv64a6_imafdc_sv39.yaml` | cv64a6_imafdc_sv39 | ~200 |
| `testlist_riscv-arch-test-cv32a65x.yaml` | cv32a65x | ~180 |
| `testlist_riscv-mmu-sv32-arch-test-cv32a6_imac_sv32.yaml` | cv32a6_imac_sv32 | ~50 |

**C. Custom Tests**

| Testlist 文件 | 测试内容 | 测试数量 |
|--------------|---------|---------|
| `testlist_custom.yaml` | 自定义测试模板 | 可配置 |
| `testlist_csr_embedded.yaml` | CSR 嵌入式测试 | ~20 |
| `testlist_riscv-csr-access-test-cv32a60x.yaml` | CSR 访问测试 | ~30 |
| `testlist_riscv-csr-access-test-cv32a65x.yaml` | CSR 访问测试 | ~30 |
| `testlist_cvxif.yaml` | CVXIF 扩展 | ~15 |
| `testlist_interrupt.yaml` | 中断测试 | ~10 |
| `testlist_pmp-cv32a65x.yaml` | PMP 测试 | ~20 |
| `testlist_hwconfig.yaml` | 硬件配置 | ~10 |
| `testlist_issues.yaml` | Bug 修复验证 | 可变 |

**D. ISA Coverage Tests**

| Testlist 文件 | 测试类型 |
|--------------|---------|
| `testlist_isacov.yaml` | branch_test, load_reg_hazard, seq_test, illegal_test 等 |

### 3.2 riscv-dv Testlist

**位置**：`verif/sim/dv/target/<target>/testlist.yaml`

**支持的目标**：
- `rv32imcb`
- `rv32imc`
- `rv32imc_sv32`
- `rv32i`
- `rv32imafdc`
- `rv64gc`
- `rv64imc`
- `rv64imcb`
- `rv64imafdc`
- `rv64gcv`
- `multi_harts`
- `ml`（机器学习扩展）

**测试类型**：
```yaml
# 示例：rv64gc/testlist.yaml
- test: riscv_arithmetic_basic_test
  iterations: 10
  gen_opts: --num_of_tests=5

- test: riscv_load_store_test
  iterations: 10

- test: riscv_mmu_stress_test
  iterations: 10

- test: riscv_floating_point_rand_test
  iterations: 10

- test: riscv_amo_test
  iterations: 5
```

### 3.3 CVA6-DV Testlist

**位置**：`verif/sim/cva6_base_testlist.yaml`

**测试内容**：
```yaml
# 算术测试（400 iterations）
- test: corev_rand_arithmetic_base_test
  iterations: 400

# 冒险测试（300 iterations）
- test: corev_rand_load_reg_hazard_test
  iterations: 300

# 非法指令（220 iterations）
- test: corev_rand_illegal_instr_test
  iterations: 220

# MMU 压力测试（200 iterations）
- test: corev_rand_mmu_stress_test
  iterations: 200

# Load/Store（400 iterations）
- test: corev_rand_load_store_test
  iterations: 400

# Jump 测试（200 iterations）
- test: corev_rand_jump_stress_test
  iterations: 200
```

### 3.4 测试矩阵总结

| 测试套件 | 测试数量 | 运行时间（Verilator）| 运行时间（VCS）|
|---------|---------|---------------------|---------------|
| riscv-tests (RV64) | ~350 | 2-4 h | 30-60 min |
| riscv-tests (RV32) | ~250 | 1-2 h | 20-40 min |
| riscv-arch-test | ~200 | 1-2 h | 20-30 min |
| riscv-dv (100 iter) | ~600 | 4-6 h | 1-2 h |
| riscv-dv (1000 iter) | ~6000 | 24-48 h | 6-12 h |
| Benchmarks | ~5 | 30 min | 10 min |
| Custom tests | ~100 | 1 h | 20 min |

---

## 四、仿真环境和工具链

### 4.1 verif/sim/ 目录结构

```
verif/sim/
├── Makefile                    # 仿真 Makefile（主要入口）
├── cva6.py                     # Python 测试框架（55KB）
├── cva6.yaml                   # ISS 配置
├── cva6-simulator.yaml         # 仿真器配置
├── setup-env.sh                # 环境配置脚本
├── cva6_base_testlist.yaml     # CVA6-DV 测试列表
├── cva6_spike_log_to_trace_csv.py  # Spike 日志转换
├── verilator_log_to_trace_csv.py   # Verilator 日志转换
├── dv/                         # RISC-V DV 框架
│   ├── run.py                  # 通用测试运行器
│   ├── cov.py                  # 覆盖率收集
│   ├── scripts/
│   ├── src/
│   └── target/
└── out_<date>/                 # 仿真输出（临时）
```

### 4.2 支持的仿真器

#### **Makefile Targets**

| Target | 仿真器 | Testbench | License | 用途 |
|--------|-------|-----------|---------|------|
| `veri-testharness` | Verilator | APU | 免费 | PR smoke test |
| `veri-testharness-pk` | Verilator + PK | APU | 免费 | Linux 测试 |
| `vcs-testharness` | VCS | APU | 商业 | Nightly |
| `vcs-uvm` | VCS | UVM | 商业 | Weekly + Coverage |
| `questa-testharness` | QuestaSim | APU | 商业 | Nightly |
| `questa-uvm` | QuestaSim | UVM | 商业 | Weekly + Coverage |
| `xrun-testharness` | Xcelium | APU | 商业 | 可选 |
| `xrun-uvm` | Xcelium | UVM | 商业 | 可选 |
| `spike` | Spike ISS | - | 免费 | 参考模型 |

#### **仿真器版本要求**

| 仿真器 | 推荐版本 | 最低版本 |
|-------|---------|---------|
| Verilator | v5.008 | v4.210 |
| Spike | vendorized | - |
| VCS | 2021.09+ | 2020.03 |
| QuestaSim | 2021.3+ | 2020.1 |
| Xcelium | 20.09+ | 19.03 |

### 4.3 工具链和依赖

#### **RISC-V Toolchain**

**GitHub Actions 使用的版本**：
- **来源**：Embecosm 预编译版本
- **版本**：riscv32-embecosm-ubuntu2204-gcc13.2.0
- **下载脚本**：`ci/install-toolchain.sh`
- **安装路径**：`tools/riscv-toolchain/`

**组件**：
```bash
riscv32-unknown-elf-gcc
riscv32-unknown-elf-g++
riscv32-unknown-elf-as
riscv32-unknown-elf-ld
riscv32-unknown-elf-objcopy
riscv32-unknown-elf-objdump
riscv32-unknown-elf-nm
```

#### **Verilator**

**版本**：v5.008
**补丁**：`verif/regress/verilator-v5.patch`
**构建时间**：~15 分钟（NUM_JOBS=8）
**安装脚本**：`verif/regress/install-verilator.sh`

**构建步骤**：
```bash
git clone https://github.com/verilator/verilator.git
cd verilator
git checkout v5.008
patch -p1 < $CVA6_REPO_DIR/verif/regress/verilator-v5.patch
autoconf
./configure --prefix=$PWD/../tools/verilator
make -j$NUM_JOBS
make install
```

#### **Spike**

**来源**：Vendorized（verif/core-v-verif/vendor/riscv/riscv-isa-sim）
**依赖**：
- boost（可选）
- yaml-cpp（必需，静态 + 动态库）

**构建步骤**：
```bash
cd verif/core-v-verif/vendor/riscv/riscv-isa-sim
# 构建 yaml-cpp
./build.sh yaml
# 构建 Spike
mkdir -p build
cd build
../configure --prefix=$SPIKE_INSTALL_DIR --with-yaml-cpp=$YAML_DIR
make -j$NUM_JOBS
make install
```

**扩展支持**：
- CVA6 定制扩展（libcustomext）
- CVXIF 协处理器接口

#### **Python 依赖**

**RISC-V DV 依赖**（`verif/sim/dv/requirements.txt`）：
```
PyYAML>=5.1
```

**系统依赖**（`ci/install-prereq.sh`）：
```bash
apt-get install -y \
  device-tree-compiler \
  libfl-dev \
  help2man \
  python3 \
  python3-pip
```

---

## 五、Coverage 系统

### 5.1 Code Coverage 配置

#### **仿真器 Coverage 选项**

**VCS**（`verif/sim/cva6-simulator.yaml`）：
```yaml
vcs:
  cov_opts: >
    -cm line+cond+fsm+tgl+branch+assert
    -cm_dir <cov_dir>/vcs.d
```

**QuestaSim**：
```bash
# 编译时
vlog +cover=bcfst ...

# 运行时
vsim -coverage ...

# 合并 coverage
vcover merge merged.ucdb test1.ucdb test2.ucdb ...

# 生成报告
vcover report -html -htmldir cov_html merged.ucdb
```

#### **Coverage Database 位置**

```
verif/sim/
├── vcs_results/
│   └── default/
│       └── vcs.d/
│           └── simv.vdb/          # VCS coverage
├── questa_results/
│   └── coverage.ucdb              # Questa coverage
└── cov_html/                      # HTML 报告
```

### 5.2 Functional Coverage

**定义位置**：
- `verif/env/uvme/cov/uvme_isa_covg.sv` - ISA covergroups
- `verif/env/uvme/cov/uvme_interrupt_covg.sv` - 中断覆盖率
- `verif/env/uvme/cov/uvme_exception_covg.sv` - 异常覆盖率
- `verif/env/uvme/cov/uvme_illegal_instr_covg.sv` - 非法指令
- `verif/env/uvme/cov/uvme_axi_covg.sv` - AXI 总线
- `verif/env/uvme/cov/uvme_cvxif_covg.sv` - CVXIF 接口

**RISC-V DV Coverage**：
- `verif/sim/dv/src/riscv_instr_cover_group.sv`

### 5.3 Verification Plan (VPlan)

**文件**：`verif/sim/cva6.hvp`（Synopsys Verdi 格式）
**Modifier**：`verif/sim/modifier_embedded.hvp`（嵌入式配置过滤器）

**查看命令**：
```bash
verdi -cov -covdir vcs_results/default/vcs.d/simv.vdb \
      -plan cva6.hvp -mod modifier_embedded.hvp
```

### 5.4 Coverage 报告生成

**GitLab CI Job**：`code_coverage-report`

**依赖**：
- `generated_tests`（6 个随机测试 job）
- `directed_isacov-tests`
- `csr_embedded_tests`

**脚本**：`.gitlab-ci/scripts/report_coverage.py`

**输出**：
- `artifacts/cov_reports/` - 合并的 coverage 报告
- HTML dashboard

---

## 六、报告和 Dashboard 系统

### 6.1 报告格式

**YAML 格式**（`.gitlab-ci/scripts/report_builder.py`）：

```yaml
job_name: smoke-tests cv64a6_imafdc_sv39
status: PASSED  # 或 FAILED
metrics:
  - type: TableStatusMetric
    name: Test Results
    data:
      - test: rv64ui-p-add
        status: PASSED
        cycles: 1234
      - test: rv64mi-p-csr
        status: PASSED
        cycles: 5678
  - type: TableMetric
    name: Coverage
    data:
      - module: Frontend
        line_cov: 95.2%
        branch_cov: 92.1%
      - module: Execute
        line_cov: 93.8%
        branch_cov: 90.5%
```

### 6.2 Dashboard 集成

**流程**：
```
1. 每个 job 生成 YAML 报告 → artifacts/reports/<job_name>.yml
2. `merge reports` job 合并所有报告 → pipeline_report_<id>.yml
3. 推送到 Dashboard Git 仓库
4. Dashboard CI 生成 HTML 页面
5. 发布到内网：https://riscv-ci.pages.thales-invia.fr/dashboard/
6. `github_integration.py` 在 GitHub PR 中添加评论
```

**Dashboard URL**（仅 Thales 内网可访问）：
- Master 分支：https://riscv-ci.pages.thales-invia.fr/dashboard/dashboard_cva6.html

**GitHub 集成**：
- Workflow：`.github/workflows/dashboard-done.yml`
- 触发：workflow_dispatch（由 GitLab CI 调用）
- 作用：在 PR 中添加 Dashboard 链接

---

## 七、当前 CI 系统的限制和风险

### 7.1 已知限制

| 限制类型 | 描述 | 影响 |
|---------|------|------|
| **GitLab CI 依赖 Thales 基础设施** | 使用私有 GitLab 实例和 self-hosted runners | OpenHW 无法直接控制 |
| **商业 EDA 工具依赖** | VCS, QuestaSim, Spyglass 需要 license | 限制社区贡献者使用 |
| **Dashboard 不公开** | Dashboard 仅 Thales 内网可访问 | 社区无法查看回归结果 |
| **Coverage 仅商业工具** | Verilator 不支持 coverage | PR-level 无 coverage 数据 |
| **UVM 环境未完全开放** | UVM testbench 需要商业仿真器 | 社区无法使用 |

### 7.2 技术债务

| 问题 | 描述 | 优先级 |
|------|------|--------|
| **Verilator 版本锁定** | 使用 v5.008 + 补丁，未跟进最新版本 | 中 |
| **测试重复** | riscv-compliance 和 riscv-arch-test 功能重叠 | 低 |
| **缺少 DSim 支持** | 计划中但未实现 | 高 |
| **Coverage 数据库过大** | 长时间回归后 coverage DB 可达 10+ GB | 中 |
| **报告系统复杂** | 多个 Python 脚本维护成本高 | 低 |

### 7.3 安全和合规风险

| 风险 | 描述 | 规避策略 |
|------|------|---------|
| **License 并发限制** | VCS/Questa license 可能被其他项目占用 | 使用 license 排队机制 |
| **Self-hosted runner 安全** | Runner 可执行任意代码 | 使用隔离环境、定期审计 |
| **Secrets 泄露** | GitLab 变量可能包含敏感信息 | 使用 masked variables |
| **Supply chain 攻击** | 第三方依赖（toolchain, verilator）| 使用 hash 验证、镜像仓库 |

### 7.4 性能瓶颈

| 瓶颈 | 影响 | 改进方向 |
|------|------|---------|
| **Verilator 编译慢** | 每次 clean build 需 30+ 分钟 | 使用 incremental build |
| **Coverage merge 慢** | 合并 1000+ 测试的 coverage 需 1+ 小时 | 增量 coverage |
| **Artifact 传输慢** | GitLab artifacts 可达数 GB | 压缩、选择性上传 |
| **Serial 测试执行** | 部分测试串行运行 | 并行化 |

---

## 八、对比：GitLab CI vs GitHub Actions

| 特性 | GitLab CI | GitHub Actions |
|------|-----------|---------------|
| **触发机制** | 复杂（4 种 CI_KIND）| 简单（push, PR）|
| **Stages** | 6 个阶段，依赖明确 | 扁平化 jobs |
| **仿真器** | Verilator, VCS, Questa, Xcelium | 仅 Verilator |
| **测试覆盖** | 完整（smoke + regression + coverage）| 仅 smoke + arch-test |
| **运行时间** | Smoke: 10-30 min, Full: 6-24 h | 30-40 min |
| **Artifacts** | 完整日志 + coverage | 仅测试日志 |
| **报告** | Dashboard + YAML | 简单 log |
| **可见性** | 内网 | 公开（GitHub）|
| **成本** | Self-hosted（内部成本）| 免费（开源项目）|

**互补关系**：
- **GitHub Actions**：社区友好，PR-level 快速反馈
- **GitLab CI**：专业验证，完整回归和 coverage

---

## 九、推荐改进方向

### 9.1 短期改进（1-2 月）

1. **添加 DSim 支持**
   - 集成 DSim 到 Makefile
   - 创建 DSim smoke test
   - 添加到 GitHub Actions（如果 license 允许）

2. **优化 GitHub Actions**
   - 增加 cache 命中率（当前 ~60%，目标 >80%）
   - 减少 smoke test 运行时间（当前 30 min，目标 <15 min）
   - 添加 PR 评论（显示测试结果摘要）

3. **文档化**
   - 创建 CI 维护手册
   - 添加故障排查指南
   - 录制视频教程

### 9.2 中期改进（3-6 月）

1. **统一报告系统**
   - 使用 GitHub Pages 或独立服务器
   - 公开 Dashboard（社区可见）
   - 集成 coverage 趋势图

2. **Coverage 优化**
   - 实现增量 coverage
   - 减少 coverage DB 大小
   - 添加 Verilator coverage 支持（如果可能）

3. **并行化测试**
   - 使用 GNU Parallel 或 pytest-xdist
   - 减少 50% 回归时间

### 9.3 长期改进（6-12 月）

1. **完全开源的 CI**
   - 所有 CI 迁移到 GitHub Actions
   - 使用开源工具（Verilator, Spike）
   - 公开所有测试结果

2. **智能测试选择**
   - 根据代码变更自动选择相关测试
   - 减少不必要的测试运行

3. **自动 Bisect**
   - 失败自动定位引入 bug 的 commit
   - 自动生成最小复现用例

---

## 十、关键文件路径速查

### CI 配置
- `.gitlab-ci.yml` - GitLab CI 主配置
- `.github/workflows/ci.yml` - GitHub Actions 主配置
- `ci/setup.sh` - GitHub Actions 安装脚本

### 仿真环境
- `verif/sim/Makefile` - 仿真 Makefile
- `verif/sim/cva6.py` - Python 测试框架
- `verif/sim/setup-env.sh` - 环境配置
- `verif/sim/cva6.yaml` - ISS 配置
- `verif/sim/cva6-simulator.yaml` - 仿真器配置

### 测试套件
- `verif/tests/testlist_*.yaml` - 28 个 testlist
- `verif/sim/dv/target/*/testlist.yaml` - RISC-V DV testlist
- `verif/sim/cva6_base_testlist.yaml` - CVA6-DV testlist

### 回归脚本
- `verif/regress/smoke-tests-*.sh` - Smoke tests
- `verif/regress/dv-*.sh` - 完整回归
- `verif/regress/install-*.sh` - 工具安装

### 报告系统
- `.gitlab-ci/scripts/report_*.py` - 报告生成
- `.gitlab-ci/scripts/merge_job_reports.py` - 报告合并
- `.gitlab-ci/scripts/github_integration.py` - GitHub 集成

### Coverage
- `verif/sim/cva6.hvp` - Verification Plan
- `verif/env/uvme/cov/*.sv` - Functional coverage

---

**文档维护**：本清单基于代码分析生成，请定期更新以反映最新状态。

**更新记录**：
- v1.0 (2026-01-17): 初始版本，基于 master 分支 commit 59f73d27
