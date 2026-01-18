# CVA6 OpenHW Regression Capability - 深度任务分析

**分析日期**: 2026-01-18
**任务来源**: 领导指派
**分析人**: Junchao
**分析深度**: ⭐⭐⭐⭐⭐ (Think Harder Mode)

---

## 📋 任务原文

```
Stand-up an OpenHW regression capability for the CVA6:
1. Port the CVA6 APU testbench to run with the latest Verilator, plus DSim and Questasim.
2. Port the CVA6 UVM testbench to run with DSim and Questasim.
3. Create a GitHub action to run CVA6-APU on Verilator whenever a Pull-Request to the RTL is made.
4. Run weekly regressions of the CVA6 UVM testbench with both DSim and Questasim.
5. Develop a method of posting weekly regression results (tests run, tests failed, code coverage
   and functional coverage) to a publicly visible website.
```

---

## 🎯 执行摘要

### 战略目标
建立 **OpenHW 自主可控的 CVA6 回归测试能力**，脱离对 Thales 内部 GitLab CI 的依赖。

### 关键挑战
| 挑战 | 难度 | 影响 | 优先级 |
|------|------|------|--------|
| DSim/QuestaSim license 获取和配置 | ⭐⭐⭐⭐ | 阻塞性 | P0 |
| UVM testbench 移植到新仿真器 | ⭐⭐⭐⭐⭐ | 高 | P0 |
| 公开网站发布（隐私和安全） | ⭐⭐⭐⭐ | 中 | P1 |
| Self-hosted runner 资源和维护 | ⭐⭐⭐ | 中 | P1 |
| Weekly regression 运行时间（6-12hr）| ⭐⭐⭐ | 中 | P2 |

### 预计时间线
**总时间**: 8-10 周（全职工作）
- **Phase 1** (Week 1-2): Verilator APU + GitHub Actions
- **Phase 2** (Week 3-5): DSim/QuestaSim APU 移植
- **Phase 3** (Week 6-8): UVM testbench 移植
- **Phase 4** (Week 9-10): 报告系统和优化

---

## 一、任务分解与技术深度分析

### Task 1: Port CVA6 APU testbench to Verilator/DSim/QuestaSim

#### 1.1 什么是 APU Testbench？

**APU** = Application Processing Unit（应用处理单元）

**CVA6 APU testbench** 位于 `corev_apu/tb/`，是 **core-level testbench**：
- **核心文件**:
  - `ariane_tb.sv` - 主 testbench
  - `ariane_testharness.sv` - Verilator wrapper
  - `ariane_peripherals.sv` - 外设模拟（UART, Debug Module）
- **功能**:
  - 加载 ELF 程序到内存
  - 运行 RISC-V 测试（riscv-tests, riscv-arch-test）
  - 与 Spike ISS 进行 Tandem simulation（RVFI）
  - 生成波形和 trace

**当前支持的仿真器**:
```bash
# 从 Makefile 和 .github/workflows/ci.yml 分析
✅ Verilator (veri-testharness)  - 当前 GitHub Actions 使用
✅ VCS (vcs-testharness)         - GitLab CI 使用
❌ Xcelium (xcelium)             - 部分支持
❌ DSim                           - 未支持
❌ QuestaSim                      - 未支持
```

---

#### 1.2 Verilator 移植状态

**当前状态**: ✅ **已支持** (Verilator v5.008)

**证据**:
```yaml
# .github/workflows/ci.yml:67
matrix:
  simulator: [ veri-testharness ]

# verif/regress/smoke-tests-cv64a6_imafdc_sv39.sh
DV_SIMULATORS=veri-testharness,spike
```

**存在的问题**:
1. **版本锁定不严格**:
   - 当前使用 Verilator v5.008
   - "latest Verilator" = v5.030+ (2026年最新)
   - **风险**: 新版本可能引入不兼容的变化

2. **性能问题**:
   - Verilator 编译时间: ~5-10 分钟（大型设计）
   - 仿真速度: 比商业工具慢 2-5x
   - **缓解**: 使用 GitHub Actions cache

3. **Trace 功能限制**:
   - Verilator 仅支持 FST/VCD 波形
   - 不支持 UVM/SystemVerilog 高级特性

**Action Items**:
- [ ] **测试 Verilator v5.030** 兼容性
- [ ] **更新 install-verilator.sh** 脚本到最新版本
- [ ] **验证 Spike tandem** 在新版本下工作
- [ ] **Benchmark** 编译和仿真时间

**预计工作量**: 2-3 天

---

#### 1.3 DSim 移植（重点）

**DSim** = Metrics Design Automation 的 **DSim Cloud**
- **优势**: 速度快（比 Verilator 快 2-3x），云端 license，支持 UVM
- **挑战**: CVA6 **从未在 DSim 上运行过**

**移植步骤详解**:

##### Step 1: 环境配置 (Day 1-2)

```bash
# 1. 安装 DSim
# 需要从 Metrics 获取安装包和 license
wget https://metrics.ca/downloads/dsim-<version>.tar.gz
tar -xzf dsim-<version>.tar.gz
export PATH=$PWD/dsim/bin:$PATH

# 2. 验证 license
dsim -version
dsim -licstat
# 预期输出: "License valid until: YYYY-MM-DD"

# 3. 配置环境变量
export DSIM_HOME=$PWD/dsim
export DSIM_LIB_PATH=$DSIM_HOME/lib
```

**关键问题**:
- ❓ OpenHW 是否已有 DSim license？
- ❓ License 类型：Node-locked vs Floating？
- ❓ 并发数量限制？

---

##### Step 2: 创建 DSim Makefile target (Day 3-5)

**需要修改的文件**: `verif/sim/Makefile`

```makefile
# 新增 DSim targets (参考 VCS 实现)

DSIM_WORK_DIR = $(CVA6_REPO_DIR)/verif/sim/dsim_results/default/dsim.d

# DSim 编译选项
DSIM_COMP_FLAGS = \
  -timescale 1ns/1ps \
  -sv \
  -uvm \
  +define+DSIM \
  +define+$(TARGET_CFG) \
  $(if $(DEBUG), -debug) \
  $(cov-comp-opt)

# DSim 运行选项
DSIM_RUN_FLAGS = \
  +permissive \
  +tohost_addr=$(shell $$RISCV/bin/riscv64-unknown-elf-nm -B $(elf) | grep -w tohost | cut -d' ' -f1) \
  $(if $(TRACE_FAST), +trace) \
  $(cov-run-opt)

dsim-testharness:
	@echo "[DSIM] Building testharness for target=$(target)"
	mkdir -p $(DSIM_WORK_DIR)
	cd $(DSIM_WORK_DIR) && dsim \
	  $(DSIM_COMP_FLAGS) \
	  -f $(FLIST_TB) \
	  -f $(FLIST_CORE) \
	  -top ariane_testharness \
	  -genimage $(DSIM_WORK_DIR)/dsim.so

	@echo "[DSIM] Running test: $(elf)"
	cd $(DSIM_WORK_DIR) && dsim \
	  $(DSIM_RUN_FLAGS) \
	  -image $(DSIM_WORK_DIR)/dsim.so \
	  -waves $(DSIM_WORK_DIR)/waves.mxd

dsim_clean:
	rm -rf $(DSIM_WORK_DIR)
```

**关键技术挑战**:

1. **+define 差异**:
   - VCS: `+define+MACRO`
   - DSim: `-D MACRO` 或 `+define+MACRO` (需验证)

2. **文件列表处理**:
   - CVA6 使用 `${CVA6_REPO_DIR}` 环境变量
   - DSim 可能需要绝对路径或 `-incdir` 选项

3. **SystemVerilog 特性兼容性**:
   - CVA6 使用 SV 2012 特性（interface, package, assertion）
   - DSim 支持度：需要测试

4. **Spike Tandem 集成**:
   - 需要通过 DPI-C 连接 Spike
   - VCS 使用 `$c()` 调用，DSim 语法可能不同

**测试计划**:
```bash
# 最小测试
cd verif/sim
make dsim-testharness target=cv64a6_imafdc_sv39 elf=../../tmp/rv64ui-p-add

# 预期输出
# [DSIM] Building testharness...
# [DSIM] Compile time: ~30s
# [DSIM] Running test...
# [DSIM] Simulation time: ~5s
# Test PASSED: rv64ui-p-add
```

**预计工作量**: 5-7 天（含调试）

---

##### Step 3: Smoke Test 验证 (Day 6-7)

```bash
# 创建 DSim smoke test 脚本
cat > verif/regress/smoke-tests-dsim-cv64a6.sh <<'EOF'
#!/bin/bash
set -e

export DV_SIMULATORS=dsim-testharness
export DV_TARGET=cv64a6_imafdc_sv39

cd verif/sim
python3 cva6.py \
  --target $DV_TARGET \
  --iss $DV_SIMULATORS \
  --iss spike \
  --iss_yaml cva6.yaml \
  --test rv64ui-p-add \
  --test rv64ui-p-sub \
  --test rv64ui-p-and \
  --test rv64um-p-mul \
  --test rv64ua-p-amoadd

echo "DSim smoke test PASSED"
EOF

chmod +x verif/regress/smoke-tests-dsim-cv64a6.sh
bash verif/regress/smoke-tests-dsim-cv64a6.sh
```

**验收标准**:
- ✅ 至少 5 个 riscv-tests 通过
- ✅ Spike tandem 匹配（0 mismatches）
- ✅ 运行时间 < 5 分钟（smoke test）

---

#### 1.4 QuestaSim 移植

**QuestaSim** (原 ModelSim) = Siemens EDA 商业仿真器
- **优势**: 成熟稳定，广泛使用，UVM 支持好
- **挑战**: License 昂贵，但 OpenHW 应该已有

**当前状态**: ❌ **未支持**（但 Makefile 中有 `vsim` 相关代码）

**移植步骤**（类似 DSim，但更简单）:

```makefile
# verif/sim/Makefile

QUESTA_WORK_DIR = $(CVA6_REPO_DIR)/verif/sim/questa_results/default/questa.d

questa-testharness:
	@echo "[QUESTA] Building testharness"
	mkdir -p $(QUESTA_WORK_DIR)
	cd $(QUESTA_WORK_DIR) && vlib work
	cd $(QUESTA_WORK_DIR) && vlog \
	  -sv \
	  +define+QUESTA \
	  +define+$(TARGET_CFG) \
	  -f $(FLIST_TB) \
	  -f $(FLIST_CORE) \
	  -work work

	@echo "[QUESTA] Running test"
	cd $(QUESTA_WORK_DIR) && vsim \
	  -c \
	  -do "run -all; quit" \
	  work.ariane_testharness \
	  +permissive \
	  $(QUESTA_RUN_FLAGS)
```

**关键差异** (QuestaSim vs VCS/DSim):
1. **编译流程**: `vlib` → `vlog` → `vsim` (3步)
2. **工作库**: 使用 `work` 库（需要 `vlib work`）
3. **波形格式**: `.wlf` (vs VCS `.vpd`, DSim `.mxd`)

**预计工作量**: 3-5 天

---

#### 1.5 任务1 总结

| 仿真器 | 当前状态 | 移植难度 | 预计时间 | 关键风险 |
|--------|---------|---------|---------|---------|
| **Verilator latest** | 已支持v5.008 | ⭐ 简单 | 2-3天 | 版本兼容性 |
| **DSim** | 未支持 | ⭐⭐⭐⭐⭐ 困难 | 5-7天 | License, 兼容性 |
| **QuestaSim** | 未支持 | ⭐⭐⭐ 中等 | 3-5天 | License |

**总工作量 (Task 1)**: **10-15 天**

**交付物**:
- ✅ `make dsim-testharness` 工作
- ✅ `make questa-testharness` 工作
- ✅ DSim/QuestaSim smoke test 脚本
- ✅ 更新 Verilator 到 v5.030+
- ✅ 文档：移植指南

---

## 二、Task 2: Port CVA6 UVM testbench to DSim/QuestaSim

### 2.1 什么是 UVM Testbench？

**UVM** = Universal Verification Methodology（通用验证方法学）

**CVA6 UVM testbench** 位于：
- `verif/tb/uvmt/` - Testbench top-level
- `verif/env/uvme/` - UVM environment
- `verif/tests/uvmt/` - UVM tests

**架构**:
```
uvmt_cva6_tb.sv (top)
  ├─ uvmt_cva6_dut_wrap.sv (DUT wrapper)
  ├─ uvme_cva6_env.sv (UVM env)
  │   ├─ uvma_cva6_core_cntrl_agent.sv (control agent)
  │   ├─ uvme_cva6_sb.sv (scoreboard)
  │   ├─ uvme_cva6_cov_model.sv (coverage model)
  │   └─ cva6_csr_reg_block.sv (CSR register model)
  └─ uvmt_cva6_test (test cases)
```

**当前支持的仿真器**:
```bash
# 从 verif/sim/Makefile:271-290
✅ VCS (vcs_uvm_comp, vcs_uvm_run)
✅ Xcelium (xrun_uvm - 部分)
❌ DSim
❌ QuestaSim
❌ Verilator (不支持 UVM)
```

---

### 2.2 UVM 移植的复杂度分析

**为什么 UVM 移植比 APU 难 5 倍？**

| 维度 | APU Testbench | UVM Testbench | 差异倍数 |
|------|--------------|--------------|---------|
| **代码量** | ~5,000 行 | ~20,000+ 行 | 4x |
| **依赖库** | 无（纯 SV） | UVM 1.2, DPI-C | 复杂 |
| **编译选项** | 简单 | 需要 `-uvm`, `-ntb_opts` | 复杂 |
| **调试难度** | 低（直接 trace） | 高（UVM phases, TLM） | 5x |
| **Coverage** | 基本 | Functional coverage | 复杂 |

**UVM 特定的挑战**:

1. **UVM 库版本**:
   - VCS 内置 UVM 1.2
   - DSim 需要指定 UVM 库路径
   - QuestaSim 内置 UVM 1.1d/1.2

2. **DPI-C 接口**:
   - CVA6 使用 DPI-C 连接 C++ 模型（Spike）
   - 不同仿真器的 DPI-C 语法略有差异

3. **UVM Phases**:
   - build_phase, connect_phase, run_phase, etc.
   - 需要所有 agents 正确初始化

4. **Register Model**:
   - `cva6_csr_reg_block.sv` 使用 UVM RAL (Register Abstraction Layer)
   - 需要正确的 adapter 和 predictor

---

### 2.3 DSim UVM 移植步骤

#### Step 1: 配置 UVM 库 (Day 1)

```bash
# DSim 需要外部 UVM 库
# 方法1: 使用 Accellera UVM 1.2
wget https://www.accellera.org/images/downloads/standards/uvm/uvm-1.2.tar.gz
tar -xzf uvm-1.2.tar.gz
export UVM_HOME=$PWD/uvm-1.2

# 方法2: 使用 DSim 自带 UVM
export UVM_HOME=$DSIM_HOME/uvm-1.2

# 验证 UVM
dsim -sv -uvm -f $UVM_HOME/src/uvm.f -top uvm_pkg -compile_only
```

---

#### Step 2: 修改 Makefile (Day 2-4)

```makefile
# verif/sim/Makefile - 添加 DSim UVM targets

UVM_VERBOSITY ?= UVM_MEDIUM
UVM_TESTNAME  ?= uvmt_cva6_firmware_test

DSIM_UVM_COMP_FLAGS = \
  -timescale 1ns/1ps \
  -sv \
  -uvm \
  -genimage $(DSIM_WORK_DIR)/dsim_uvm.so \
  +define+DSIM \
  +define+UVM_NO_DPI \
  -f $(UVM_HOME)/src/uvm.f \
  -f $(CVA6_REPO_DIR)/verif/tb/uvmt/uvmt_cva6.flist \
  +incdir+$(CVA6_REPO_DIR)/verif/env/uvme \
  $(cov-comp-opt)

DSIM_UVM_RUN_FLAGS = \
  -image $(DSIM_WORK_DIR)/dsim_uvm.so \
  +UVM_TESTNAME=$(UVM_TESTNAME) \
  +UVM_VERBOSITY=$(UVM_VERBOSITY) \
  -waves $(DSIM_WORK_DIR)/waves_uvm.mxd \
  $(cov-run-opt)

dsim_uvm_comp:
	@echo "[DSIM-UVM] Compiling UVM testbench"
	mkdir -p $(DSIM_WORK_DIR)
	cd $(DSIM_WORK_DIR) && dsim \
	  $(DSIM_UVM_COMP_FLAGS) \
	  -top uvmt_cva6_tb

dsim_uvm_run: dsim_uvm_comp
	@echo "[DSIM-UVM] Running UVM test: $(UVM_TESTNAME)"
	cd $(DSIM_WORK_DIR) && dsim \
	  $(DSIM_UVM_RUN_FLAGS)

dsim-uvm: dsim_uvm_comp dsim_uvm_run
```

---

#### Step 3: 处理兼容性问题 (Day 5-10)

**常见兼容性问题列表**:

1. **UVM_NO_DPI 定义**:
```systemverilog
// 如果 DSim 不支持某些 DPI functions
`ifdef DSIM
  `define UVM_NO_DPI
`endif
```

2. **时间单位**:
```systemverilog
// VCS 默认: 1ns/1ps
// DSim 可能需要显式指定
`timescale 1ns/1ps
```

3. **宏定义差异**:
```systemverilog
// VCS: +define+MACRO=VALUE
// DSim: -D MACRO=VALUE 或 +define+MACRO=VALUE
```

4. **Coverage pragmas**:
```systemverilog
// VCS: // synopsys coverage_off
// DSim: // coverage off
`ifdef DSIM
  // coverage off
`else
  // synopsys coverage_off
`endif
```

5. **DPI-C 函数签名**:
```c
// VCS: import "DPI-C" function int spike_step();
// DSim: 可能需要 context 参数
import "DPI-C" context function int spike_step();
```

---

#### Step 4: 单元测试 (Day 11-12)

```bash
# 测试 UVM agent 是否工作
cd verif/sim
make dsim_uvm_comp target=cv64a6_imafdc_sv39

# 运行最简单的 UVM test
make dsim_uvm_run \
  target=cv64a6_imafdc_sv39 \
  UVM_TESTNAME=uvmt_cva6_firmware_test \
  elf=../../tmp/hello_world.elf

# 预期输出
# UVM_INFO @ 0ns: reporter [RNTST] Running test uvmt_cva6_firmware_test...
# UVM_INFO @ 1000ns: uvm_test_top.env.agt [AGENT] Test started
# UVM_INFO @ 50000ns: uvm_test_top.env.sb [SCOREBOARD] All checks passed
# UVM_INFO @ 50100ns: reporter [UVMTOP] Simulation PASSED
```

---

#### Step 5: 完整回归测试 (Day 13-15)

```bash
# 创建 DSim UVM regression 脚本
cat > verif/regress/uvm-regression-dsim.sh <<'EOF'
#!/bin/bash
set -e

export DV_SIMULATORS=dsim
export DV_TARGET=cv64a6_imafdc_sv39

tests=(
  "uvmt_cva6_firmware_test+rv64ui-p-add"
  "uvmt_cva6_firmware_test+rv64ui-p-sub"
  "uvmt_cva6_firmware_test+rv64um-p-mul"
  "uvmt_cva6_firmware_test+rv64ua-p-amoadd"
)

for test in "${tests[@]}"; do
  echo "Running UVM test: $test"
  make dsim-uvm \
    target=$DV_TARGET \
    UVM_TESTNAME=${test%%+*} \
    elf=../../tmp/${test##*+}.elf
done

echo "DSim UVM regression PASSED"
EOF
```

**预计工作量**: 15-20 天（含调试）

---

### 2.4 QuestaSim UVM 移植

**好消息**: QuestaSim 对 UVM 的支持非常成熟，移植难度低于 DSim。

**关键步骤**:

```makefile
# verif/sim/Makefile

QUESTA_UVM_COMP_FLAGS = \
  -sv \
  -uvm \
  +define+QUESTA \
  -f $(CVA6_REPO_DIR)/verif/tb/uvmt/uvmt_cva6.flist \
  -work $(QUESTA_WORK_DIR)/work

QUESTA_UVM_RUN_FLAGS = \
  -c \
  -do "run -all; quit" \
  +UVM_TESTNAME=$(UVM_TESTNAME) \
  +UVM_VERBOSITY=$(UVM_VERBOSITY)

questa_uvm_comp:
	mkdir -p $(QUESTA_WORK_DIR)
	cd $(QUESTA_WORK_DIR) && vlib work
	cd $(QUESTA_WORK_DIR) && vlog $(QUESTA_UVM_COMP_FLAGS)
	cd $(QUESTA_WORK_DIR) && vopt work.uvmt_cva6_tb -o uvmt_cva6_tb_opt

questa_uvm_run: questa_uvm_comp
	cd $(QUESTA_WORK_DIR) && vsim $(QUESTA_UVM_RUN_FLAGS) uvmt_cva6_tb_opt

questa-uvm: questa_uvm_comp questa_uvm_run
```

**预计工作量**: 8-10 天

---

### 2.5 任务2 总结

| 仿真器 | UVM 支持 | 移植难度 | 预计时间 | 关键风险 |
|--------|---------|---------|---------|---------|
| **DSim** | 需外部 UVM | ⭐⭐⭐⭐⭐ 很困难 | 15-20天 | UVM 兼容性, DPI-C |
| **QuestaSim** | 内置 UVM 1.2 | ⭐⭐⭐ 中等 | 8-10天 | License, 配置 |

**总工作量 (Task 2)**: **23-30 天**

**交付物**:
- ✅ `make dsim-uvm` 工作
- ✅ `make questa-uvm` 工作
- ✅ UVM regression 脚本（DSim/QuestaSim）
- ✅ 兼容性补丁文件
- ✅ 文档：UVM 移植指南

---

## 三、Task 3: GitHub Actions for CVA6-APU on Verilator

### 3.1 当前 GitHub Actions 状态

**现有 workflow**: `.github/workflows/ci.yml`

**当前配置**:
```yaml
name: ci
on: [push, pull_request]

jobs:
  execute-riscv64-tests:
    strategy:
      matrix:
        testcase: [ cv64a6_imafdc_tests, dv-riscv-arch-test ]
        config: [ cv64a6_imafdc_sv39_hpdcache, cv64a6_imafdc_sv39_wb, ... ]
        simulator: [ veri-testharness ]
```

**问题分析**:
1. ✅ **已经在运行 Verilator** on PR
2. ❌ **测试范围过大** (800+ tests, 30-40 分钟)
3. ❌ **没有仅针对 APU testbench** 的专项 job
4. ❌ **缺少失败报告和分析**

---

### 3.2 改进方案

#### 方案 A: 创建独立的 APU PR job（推荐）

```yaml
# .github/workflows/pr-apu-smoke.yml (新文件)

name: PR APU Smoke Test
on:
  pull_request:
    branches: [ master ]
    paths:
      - 'core/**'           # RTL 变更触发
      - 'corev_apu/tb/**'   # APU testbench 变更触发
      - '.github/workflows/pr-apu-smoke.yml'

jobs:
  apu-smoke-verilator:
    name: APU Smoke Test (Verilator)
    runs-on: ubuntu-latest
    timeout-minutes: 20  # 严格限制时间

    steps:
    - uses: actions/checkout@v4
      with:
        submodules: recursive

    # Cache 加速（与现有 CI 共享）
    - name: Cache toolchain
      uses: actions/cache@v3
      with:
        path: tools/riscv-toolchain/
        key: ${{ runner.os }}-toolchain-${{ hashFiles('ci/install-toolchain.sh') }}

    - name: Cache verilator
      uses: actions/cache@v3
      with:
        path: tools/verilator/
        key: ${{ runner.os }}-verilator-${{ hashFiles('verif/regress/install-verilator.sh') }}

    - name: Cache Spike
      uses: actions/cache@v3
      with:
        path: tools/spike/
        key: ${{ runner.os }}-spike-${{ hashFiles('verif/regress/install-spike.sh') }}

    # 环境配置
    - name: Setup environment
      run: |
        ci/setup.sh
        source verif/sim/setup-env.sh

    # 运行 APU smoke test
    - name: Run APU smoke test
      run: |
        cd verif/sim
        DV_SIMULATORS=veri-testharness,spike \
        DV_TARGET=cv64a6_imafdc_sv39 \
        bash ../regress/smoke-tests-cv64a6_imafdc_sv39.sh

    # 上传结果
    - name: Upload test results
      if: always()
      uses: actions/upload-artifact@v4
      with:
        name: apu-smoke-results
        path: |
          verif/sim/out_*/
          verif/sim/logfile.log
          verif/sim/*_results/

    # 生成报告
    - name: Generate test report
      if: always()
      run: |
        python3 verif/sim/report_builder.py \
          --results verif/sim/out_* \
          --format markdown \
          --output test-report.md

    # PR 评论（失败时）
    - name: Comment on PR (if failed)
      if: failure()
      uses: actions/github-script@v7
      with:
        script: |
          const fs = require('fs');
          const report = fs.readFileSync('test-report.md', 'utf8');
          github.rest.issues.createComment({
            owner: context.repo.owner,
            repo: context.repo.repo,
            issue_number: context.issue.number,
            body: `## ⚠️ APU Smoke Test Failed\n\n${report}`
          });
```

**优点**:
- ✅ 独立 workflow，不影响现有 CI
- ✅ 仅 smoke test (10-15 分钟)
- ✅ PR 评论自动通知
- ✅ Cache 加速（第二次运行 <5 分钟）

---

#### 方案 B: 修改现有 CI (最小改动)

```yaml
# .github/workflows/ci.yml (修改现有文件)

jobs:
  # 新增一个 matrix 维度
  execute-riscv64-tests:
    strategy:
      matrix:
        include:
          # 原有的 full tests
          - testcase: cv64a6_imafdc_tests
            simulator: veri-testharness
            config: cv64a6_imafdc_sv39
            test_type: full

          # 新增 APU-only smoke test
          - testcase: smoke-tests-cv64a6_imafdc_sv39
            simulator: veri-testharness
            config: cv64a6_imafdc_sv39
            test_type: apu_smoke
```

**优点**: 改动小
**缺点**: 与 full tests 混在一起，不够清晰

---

### 3.3 推荐方案

**选择方案 A**，原因：
1. 清晰独立，易于维护
2. 快速反馈（10-15 分钟）
3. 失败时自动评论 PR
4. 不影响现有 CI

**预计工作量**: 3-5 天

**交付物**:
- ✅ `.github/workflows/pr-apu-smoke.yml`
- ✅ `report_builder.py` 报告生成脚本
- ✅ PR 评论模板
- ✅ 文档：GitHub Actions 配置指南

---

## 四、Task 4: Weekly UVM Regressions (DSim + QuestaSim)

### 4.1 Weekly Regression 的目标

**目标**:
- 每周运行 **完整的 UVM 测试集**
- 使用 **DSim 和 QuestaSim** 各运行一次
- 收集 **code coverage 和 functional coverage**
- 生成 **regression 报告**

**测试规模估算**:
```
UVM Test Suite:
├─ Firmware tests: ~50 tests (hello_world, dhrystone, coremark)
├─ Compliance tests: ~800 tests (riscv-arch-test)
├─ Random tests: ~200 tests (UVM randomized)
├─ Directed tests: ~100 tests (custom)
└─ Total: ~1150 tests

Runtime estimate:
- DSim: ~6-8 hours (faster)
- QuestaSim: ~8-10 hours (slower)
- Total: ~16-18 hours (serial) or ~10 hours (parallel)
```

---

### 4.2 Weekly Regression 架构设计

#### 方案 A: GitHub Actions Scheduled Workflow（推荐用于 OpenHW）

```yaml
# .github/workflows/weekly-uvm-regression.yml

name: Weekly UVM Regression
on:
  schedule:
    # 每周日 00:00 UTC (北京时间周日 08:00)
    - cron: '0 0 * * 0'
  workflow_dispatch:  # 允许手动触发

jobs:
  # Job 1: DSim UVM Regression
  uvm-regression-dsim:
    name: UVM Regression (DSim)
    runs-on: [self-hosted, linux, dsim]  # 需要 self-hosted runner
    timeout-minutes: 600  # 10 hours

    steps:
    - uses: actions/checkout@v4
      with:
        submodules: recursive

    - name: Setup DSim environment
      run: |
        export DSIM_HOME=/opt/dsim
        export PATH=$DSIM_HOME/bin:$PATH
        dsim -version

    - name: Run UVM regression
      run: |
        cd verif/sim
        export cov=1  # Enable coverage
        bash ../regress/uvm-regression-dsim.sh

    - name: Collect coverage
      run: |
        cd verif/sim/dsim_results
        # DSim coverage merge (syntax TBD)
        dsim-cov merge -o merged.covdb */*.covdb
        dsim-cov report -html -o cov_html merged.covdb

    - name: Upload artifacts
      uses: actions/upload-artifact@v4
      with:
        name: dsim-regression-results
        path: |
          verif/sim/dsim_results/
          verif/sim/dsim_results/cov_html/

  # Job 2: QuestaSim UVM Regression
  uvm-regression-questa:
    name: UVM Regression (QuestaSim)
    runs-on: [self-hosted, linux, questa]
    timeout-minutes: 720  # 12 hours

    steps:
    - uses: actions/checkout@v4
      with:
        submodules: recursive

    - name: Setup QuestaSim environment
      run: |
        export QUESTA_HOME=/opt/questa
        export PATH=$QUESTA_HOME/bin:$PATH
        vsim -version

    - name: Run UVM regression
      run: |
        cd verif/sim
        export cov=1
        bash ../regress/uvm-regression-questa.sh

    - name: Collect coverage
      run: |
        cd verif/sim/questa_results
        vcover merge merged.ucdb */*.ucdb
        vcover report -html -htmldir cov_html merged.ucdb

    - name: Upload artifacts
      uses: actions/upload-artifact@v4
      with:
        name: questa-regression-results
        path: |
          verif/sim/questa_results/
          verif/sim/questa_results/cov_html/

  # Job 3: 生成汇总报告
  generate-report:
    name: Generate Weekly Report
    needs: [uvm-regression-dsim, uvm-regression-questa]
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v4

    - name: Download DSim results
      uses: actions/download-artifact@v4
      with:
        name: dsim-regression-results
        path: results/dsim/

    - name: Download QuestaSim results
      uses: actions/download-artifact@v4
      with:
        name: questa-regression-results
        path: results/questa/

    - name: Generate markdown report
      run: |
        python3 verif/scripts/generate_weekly_report.py \
          --dsim results/dsim/ \
          --questa results/questa/ \
          --output weekly-report-$(date +%Y-%m-%d).md

    - name: Upload report to GitHub Pages
      # 见 Task 5 详细设计
```

**关键要求**:
- ✅ Self-hosted runner（需要 DSim/QuestaSim license）
- ✅ 足够的磁盘空间（每次 regression ~50-100GB）
- ✅ 定时触发（cron schedule）
- ✅ Artifacts 上传（测试结果、coverage）

---

#### 方案 B: GitLab CI（如果 OpenHW 有内部 GitLab）

```yaml
# .gitlab-ci.yml

weekly-uvm-regression:
  stage: regression
  only:
    - schedules  # 仅定时任务触发
  script:
    - cd verif/sim
    - export cov=1
    - bash ../regress/uvm-regression-dsim.sh
    - bash ../regress/uvm-regression-questa.sh
  artifacts:
    paths:
      - verif/sim/dsim_results/
      - verif/sim/questa_results/
    expire_in: 4 weeks
  tags:
    - cva6-regression-runner
```

---

### 4.3 Regression 脚本设计

```bash
# verif/regress/uvm-regression-dsim.sh

#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd $SCRIPT_DIR/../sim

export DV_SIMULATORS=dsim
export DV_TARGET=cv64a6_imafdc_sv39
export cov=1

# 定义测试列表
TESTLISTS=(
  "../tests/testlist_riscv-tests-cv64a6_imafdc_sv39-p.yaml"
  "../tests/testlist_riscv-arch-test-cv64a6_imafdc_sv39.yaml"
  "../tests/testlist_uvm_random.yaml"
)

# 统计变量
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

echo "==================================="
echo "CVA6 UVM Regression (DSim)"
echo "Date: $(date)"
echo "Target: $DV_TARGET"
echo "==================================="

# 运行所有测试
for testlist in "${TESTLISTS[@]}"; do
  echo "Running testlist: $testlist"

  python3 cva6.py \
    --target $DV_TARGET \
    --iss dsim \
    --testlist $testlist \
    --cov \
    --output dsim_results/$(basename $testlist .yaml) \
    2>&1 | tee dsim_regression.log

  # 解析结果
  TESTS_RUN=$(grep -c "Test:" dsim_regression.log || true)
  TESTS_PASSED=$(grep -c "PASSED" dsim_regression.log || true)
  TESTS_FAILED=$(grep -c "FAILED" dsim_regression.log || true)

  TOTAL_TESTS=$((TOTAL_TESTS + TESTS_RUN))
  PASSED_TESTS=$((PASSED_TESTS + TESTS_PASSED))
  FAILED_TESTS=$((FAILED_TESTS + TESTS_FAILED))
done

# 生成摘要
echo "==================================="
echo "Regression Summary:"
echo "  Total tests:  $TOTAL_TESTS"
echo "  Passed:       $PASSED_TESTS"
echo "  Failed:       $FAILED_TESTS"
echo "  Pass rate:    $(awk "BEGIN {printf \"%.2f%%\", $PASSED_TESTS/$TOTAL_TESTS*100}")"
echo "==================================="

# 失败则退出非零
if [ $FAILED_TESTS -gt 0 ]; then
  echo "ERROR: $FAILED_TESTS tests failed"
  exit 1
fi

echo "Regression PASSED"
```

**预计工作量**: 5-7 天

---

### 4.4 Self-hosted Runner 配置

**关键基础设施需求**:

```yaml
# Self-hosted runner 规格
Hardware:
  CPU: 32+ cores (推荐 64 cores)
  Memory: 128 GB+ (推荐 256 GB)
  Disk: 2 TB NVMe SSD
  Network: 1 Gbps

Software:
  OS: Ubuntu 22.04 LTS
  DSim: latest version + floating license
  QuestaSim: 2023.4+ + floating license
  Docker: 24.0+ (optional, for isolation)

License Server:
  FlexLM server for DSim/QuestaSim
  Concurrent licenses: 2-4
  Monitoring: lmstat -a
```

**GitHub Runner 安装**:
```bash
# 在 runner 机器上
mkdir actions-runner && cd actions-runner
curl -o actions-runner-linux-x64-2.311.0.tar.gz \
  -L https://github.com/actions/runner/releases/download/v2.311.0/actions-runner-linux-x64-2.311.0.tar.gz
tar xzf ./actions-runner-linux-x64-2.311.0.tar.gz

# 配置（需要 GitHub repo admin 权限）
./config.sh --url https://github.com/openhwgroup/cva6 \
  --token <REGISTRATION_TOKEN> \
  --labels self-hosted,linux,dsim,questa

# 启动 runner
./run.sh
```

**预计工作量**: 2-3 天（假设硬件已就绪）

---

### 4.5 任务4 总结

| 子任务 | 难度 | 预计时间 | 关键依赖 |
|--------|------|---------|---------|
| Self-hosted runner 配置 | ⭐⭐⭐ | 2-3天 | 硬件、License |
| UVM regression 脚本 | ⭐⭐⭐⭐ | 5-7天 | Task 2 完成 |
| GitHub Actions workflow | ⭐⭐ | 2-3天 | Runner 就绪 |
| Coverage 收集和合并 | ⭐⭐⭐⭐ | 3-5天 | 工具文档 |

**总工作量 (Task 4)**: **12-18 天**

**交付物**:
- ✅ `.github/workflows/weekly-uvm-regression.yml`
- ✅ `verif/regress/uvm-regression-dsim.sh`
- ✅ `verif/regress/uvm-regression-questa.sh`
- ✅ Self-hosted runner 配置文档
- ✅ Coverage 收集和报告脚本

---

## 五、Task 5: Public Website for Regression Results

### 5.1 需求分析

**需要展示的数据**:
1. **测试结果**:
   - Tests run / passed / failed
   - Pass rate trend (weekly)
   - Failed test list with details

2. **Code Coverage**:
   - Line coverage %
   - Branch coverage %
   - Toggle coverage %
   - Coverage trend (weekly)

3. **Functional Coverage**:
   - Covergroup coverage %
   - Cross coverage
   - Coverage holes

4. **性能指标**:
   - Regression runtime
   - Simulation speed (cycles/second)

**安全和隐私要求**:
- ✅ 公开：测试结果、coverage 统计
- ❌ 不公开：详细 RTL 代码、仿真波形、EDA 工具版本

---

### 5.2 方案对比

| 方案 | 优点 | 缺点 | 成本 |
|------|------|------|------|
| **GitHub Pages** | 免费、简单、与 repo 集成 | 静态页面、功能有限 | $0 |
| **GitLab Pages** | 类似 GitHub Pages | 需要 GitLab 账号 | $0 |
| **AWS S3 + CloudFront** | 高可用、CDN 加速 | 配置复杂、需要 AWS 账号 | ~$5/月 |
| **自建服务器** | 完全控制 | 维护成本高 | 硬件+人力 |

**推荐**: **GitHub Pages**（最适合 OpenHW）

---

### 5.3 GitHub Pages 方案设计

#### 架构

```
openhwgroup/cva6 repo
├─ gh-pages branch (自动生成)
│   ├─ index.html (首页)
│   ├─ reports/
│   │   ├─ 2026-01-12/
│   │   │   ├─ report.html
│   │   │   ├─ coverage-dsim/
│   │   │   └─ coverage-questa/
│   │   ├─ 2026-01-19/
│   │   └─ ...
│   ├─ assets/
│   │   ├─ css/
│   │   └─ js/
│   └─ api/
│       └─ latest.json (最新结果的 JSON API)
└─ .github/workflows/weekly-uvm-regression.yml
     └─ (自动更新 gh-pages branch)
```

访问 URL: `https://openhwgroup.github.io/cva6/`

---

#### 实现步骤

**Step 1: 生成 HTML 报告**

```python
# verif/scripts/generate_weekly_report.py

import json
from datetime import datetime
from pathlib import Path

def generate_html_report(dsim_results, questa_results, output_dir):
    """生成 HTML 格式的 weekly regression 报告"""

    # 解析测试结果
    dsim_summary = parse_results(dsim_results)
    questa_summary = parse_results(questa_results)

    # 解析 coverage
    dsim_cov = parse_coverage(dsim_results / "cov_html")
    questa_cov = parse_coverage(questa_results / "cov_html")

    # 生成 HTML
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>CVA6 Weekly Regression - {datetime.now().strftime('%Y-%m-%d')}</title>
        <link rel="stylesheet" href="../../assets/css/report.css">
    </head>
    <body>
        <h1>CVA6 Weekly Regression Report</h1>
        <p>Date: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}</p>

        <h2>Summary</h2>
        <table>
            <tr>
                <th>Simulator</th>
                <th>Tests Run</th>
                <th>Tests Passed</th>
                <th>Pass Rate</th>
                <th>Line Coverage</th>
                <th>Branch Coverage</th>
            </tr>
            <tr>
                <td>DSim</td>
                <td>{dsim_summary['total']}</td>
                <td>{dsim_summary['passed']}</td>
                <td>{dsim_summary['pass_rate']:.2f}%</td>
                <td>{dsim_cov['line']:.2f}%</td>
                <td>{dsim_cov['branch']:.2f}%</td>
            </tr>
            <tr>
                <td>QuestaSim</td>
                <td>{questa_summary['total']}</td>
                <td>{questa_summary['passed']}</td>
                <td>{questa_summary['pass_rate']:.2f}%</td>
                <td>{questa_cov['line']:.2f}%</td>
                <td>{questa_cov['branch']:.2f}%</td>
            </tr>
        </table>

        <h2>Failed Tests</h2>
        <ul>
            {generate_failed_tests_list(dsim_summary['failed'])}
        </ul>

        <h2>Coverage Details</h2>
        <a href="coverage-dsim/index.html">DSim Coverage Report</a><br>
        <a href="coverage-questa/index.html">QuestaSim Coverage Report</a>

        <h2>Historical Trend</h2>
        <canvas id="trendChart"></canvas>
        <script src="../../assets/js/chart.min.js"></script>
        <script src="../../assets/js/render_trend.js"></script>
    </body>
    </html>
    """

    # 写入文件
    output_file = output_dir / "report.html"
    output_file.write_text(html)

    # 生成 JSON API
    json_data = {
        "date": datetime.now().isoformat(),
        "dsim": dsim_summary,
        "questa": questa_summary,
        "dsim_coverage": dsim_cov,
        "questa_coverage": questa_cov
    }
    json_file = output_dir / "data.json"
    json_file.write_text(json.dumps(json_data, indent=2))
```

---

**Step 2: GitHub Actions 自动发布**

```yaml
# .github/workflows/weekly-uvm-regression.yml (续)

jobs:
  # ... (前面的 dsim/questa regression jobs)

  publish-to-gh-pages:
    name: Publish Results to GitHub Pages
    needs: [generate-report]
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v4
      with:
        ref: gh-pages  # Checkout gh-pages branch

    - name: Download report artifacts
      uses: actions/download-artifact@v4
      with:
        name: weekly-report
        path: temp-report/

    - name: Organize report
      run: |
        REPORT_DATE=$(date +%Y-%m-%d)
        mkdir -p reports/$REPORT_DATE

        # 复制 HTML 报告
        cp temp-report/weekly-report-*.md reports/$REPORT_DATE/

        # 复制 coverage HTML（需要先生成）
        cp -r temp-report/dsim/cov_html reports/$REPORT_DATE/coverage-dsim
        cp -r temp-report/questa/cov_html reports/$REPORT_DATE/coverage-questa

        # 更新 latest.json
        cp reports/$REPORT_DATE/data.json api/latest.json

        # 更新 index.html (添加新的 report 链接)
        python3 scripts/update_index.py --new-report $REPORT_DATE

    - name: Commit and push
      run: |
        git config user.name "CVA6 CI Bot"
        git config user.email "ci-bot@openhwgroup.org"
        git add reports/ api/ index.html
        git commit -m "Weekly regression report: $(date +%Y-%m-%d)"
        git push origin gh-pages
```

---

**Step 3: 首页设计**

```html
<!-- index.html (在 gh-pages branch) -->
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>CVA6 Regression Dashboard</title>
    <link rel="stylesheet" href="assets/css/dashboard.css">
</head>
<body>
    <header>
        <h1>CVA6 Regression Dashboard</h1>
        <p>OpenHW Group - Public CI/Regression Results</p>
    </header>

    <main>
        <section id="latest-results">
            <h2>Latest Regression Results</h2>
            <div id="latest-summary">
                <!-- JavaScript 动态加载 api/latest.json -->
            </div>
        </section>

        <section id="historical-reports">
            <h2>Historical Reports</h2>
            <ul>
                <li><a href="reports/2026-01-19/report.html">2026-01-19</a></li>
                <li><a href="reports/2026-01-12/report.html">2026-01-12</a></li>
                <li><a href="reports/2026-01-05/report.html">2026-01-05</a></li>
                <!-- 自动生成 -->
            </ul>
        </section>

        <section id="trends">
            <h2>Coverage Trends</h2>
            <canvas id="coverageTrendChart"></canvas>
        </section>
    </main>

    <footer>
        <p>Powered by GitHub Actions | Last updated: <span id="last-update"></span></p>
    </footer>

    <script src="assets/js/dashboard.js"></script>
</body>
</html>
```

---

### 5.4 隐私和安全考虑

**公开的信息**:
- ✅ 测试名称（例如：rv64ui-p-add）
- ✅ 测试结果（PASS/FAIL）
- ✅ Coverage 百分比（line, branch, toggle）
- ✅ Regression 运行时间

**不公开的信息**:
- ❌ 详细的 RTL 源代码
- ❌ 仿真波形文件（.fsdb, .vpd）
- ❌ EDA 工具版本和 license 信息
- ❌ Self-hosted runner 的 IP 地址

**实现方法**:
```python
# 在 generate_weekly_report.py 中过滤敏感信息

def sanitize_coverage_html(coverage_dir):
    """移除 coverage HTML 中的敏感信息"""
    for html_file in coverage_dir.glob("**/*.html"):
        content = html_file.read_text()

        # 移除绝对路径
        content = re.sub(r'/home/[^/]+/.*?cva6', '/path/to/cva6', content)

        # 移除工具版本信息
        content = re.sub(r'Generated by VCS \d+\.\d+', 'Generated by VCS', content)

        html_file.write_text(content)
```

---

### 5.5 任务5 总结

| 子任务 | 难度 | 预计时间 |
|--------|------|---------|
| GitHub Pages 设置 | ⭐ | 1天 |
| HTML 报告生成脚本 | ⭐⭐⭐ | 3-4天 |
| Coverage HTML 处理 | ⭐⭐⭐⭐ | 2-3天 |
| Dashboard 前端开发 | ⭐⭐⭐ | 3-5天 |
| 安全和隐私审查 | ⭐⭐ | 1-2天 |

**总工作量 (Task 5)**: **10-15 天**

**交付物**:
- ✅ `gh-pages` branch 配置
- ✅ `verif/scripts/generate_weekly_report.py`
- ✅ `verif/scripts/update_index.py`
- ✅ Dashboard HTML/CSS/JS
- ✅ 隐私过滤脚本
- ✅ 文档：GitHub Pages 使用指南

---

## 六、总体项目计划

### 6.1 时间线和里程碑

```
Week 1-2: Phase 1 - Verilator 基础
├─ Week 1
│   ├─ 文档完成 ✅ (已完成)
│   ├─ Verilator latest 测试
│   └─ APU smoke test 优化
└─ Week 2
    ├─ GitHub Actions PR workflow
    └─ Verilator cache 优化

Week 3-5: Phase 2 - DSim/QuestaSim APU 移植
├─ Week 3
│   ├─ DSim 环境配置
│   ├─ DSim Makefile targets
│   └─ DSim smoke test
├─ Week 4
│   ├─ QuestaSim 环境配置
│   ├─ QuestaSim Makefile targets
│   └─ QuestaSim smoke test
└─ Week 5
    └─ APU 移植验收测试

Week 6-8: Phase 3 - UVM Testbench 移植
├─ Week 6
│   ├─ DSim UVM 环境配置
│   ├─ UVM 编译调试
│   └─ 处理兼容性问题
├─ Week 7
│   ├─ QuestaSim UVM 移植
│   └─ UVM regression 脚本
└─ Week 8
    └─ UVM 移植验收测试

Week 9-10: Phase 4 - Weekly Regression & 报告系统
├─ Week 9
│   ├─ Self-hosted runner 配置
│   ├─ Weekly regression workflow
│   ├─ Coverage 收集脚本
│   └─ HTML 报告生成
└─ Week 10
    ├─ GitHub Pages 配置
    ├─ Dashboard 开发
    ├─ 安全审查
    └─ 最终验收
```

---

### 6.2 关键依赖和风险

#### 关键依赖（Blockers）

| 依赖项 | 负责人 | 截止日期 | 风险等级 |
|--------|--------|---------|---------|
| **DSim license** | OpenHW IT | Week 3 Day 1 | 🔴 高 |
| **QuestaSim license** | OpenHW IT | Week 4 Day 1 | 🔴 高 |
| **Self-hosted runner 硬件** | OpenHW IT | Week 9 Day 1 | 🔴 高 |
| **GitHub repo admin 权限** | OpenHW Manager | Week 2 Day 1 | 🟡 中 |
| **License 服务器配置** | OpenHW IT | Week 3 Day 1 | 🟡 中 |

---

#### 风险评估和缓解

| 风险 | 概率 | 影响 | 缓解策略 |
|------|------|------|---------|
| **License 无法获取** | 中 | 阻塞性 | 提前 1 个月申请，准备备选方案（云端 license）|
| **UVM 兼容性问题严重** | 高 | 高 | 预留 2 周 buffer time，联系 EDA vendor 支持 |
| **Self-hosted runner 不稳定** | 中 | 中 | 配置监控和自动重启，准备备用 runner |
| **Coverage 数据过大** | 高 | 低 | 定期清理，仅保留最近 4 周数据 |
| **GitHub Pages 性能问题** | 低 | 低 | 使用 CDN，压缩 HTML |

---

### 6.3 资源需求

#### 人力资源
- **您（全职）**: 8-10 周
- **OpenHW IT（兼职）**: ~5 天（硬件、license、网络配置）
- **EDA Vendor 支持（按需）**: ~3 天（DSim/QuestaSim 技术支持）

#### 硬件资源
```
Self-hosted Runner:
- CPU: 64 cores
- Memory: 256 GB
- Disk: 2 TB NVMe SSD
- 预估成本: $8,000 - $12,000 (一次性) 或 $400/月 (云端)
```

#### License 资源
```
DSim:
- Type: Floating license
- Quantity: 2 concurrent
- Cost: ~$20,000/year (估算)

QuestaSim:
- Type: Floating license
- Quantity: 2 concurrent
- Cost: ~$30,000/year (估算)
```

---

### 6.4 成功标准

#### 必须达成（P0）
- ✅ APU testbench 在 Verilator/DSim/QuestaSim 上运行
- ✅ UVM testbench 在 DSim/QuestaSim 上运行
- ✅ GitHub Actions PR smoke test <15 分钟
- ✅ Weekly UVM regression 自动运行
- ✅ 回归结果发布到公开网站

#### 期望达成（P1）
- ✅ APU smoke test pass rate >95%
- ✅ UVM regression pass rate >90%
- ✅ Code coverage >85%
- ✅ Weekly regression <12 hours

#### 可选达成（P2）
- ⭐ Functional coverage >70%
- ⭐ Dashboard 交互式图表
- ⭐ PR 自动 bisect 失败 commit

---

## 七、建议和后续演进

### 7.1 立即行动项（本周）

1. **与领导确认**:
   - ✅ DSim/QuestaSim license 申请状态
   - ✅ Self-hosted runner 硬件预算批准
   - ✅ GitHub repo admin 权限申请
   - ✅ 时间线是否可接受（8-10 周）

2. **技术准备**:
   - ✅ 联系 Metrics（DSim vendor）获取评估 license
   - ✅ 联系 Siemens EDA（QuestaSim vendor）获取评估 license
   - ✅ 开始 Verilator latest 版本测试

3. **文档准备**:
   - ✅ 向领导展示本分析文档
   - ✅ 获得 Phase 1-4 的批准
   - ✅ 设置 weekly status meeting

---

### 7.2 未来优化方向（10 周后）

1. **性能优化**:
   - Parallel test execution（减少 50% 运行时间）
   - Incremental coverage（仅收集变更文件的 coverage）
   - Smart test selection（基于代码变更选择测试）

2. **功能增强**:
   - Automatic bisect for failed tests
   - Email notifications for regression failures
   - Slack/Teams integration

3. **Dashboard 增强**:
   - 实时 regression 进度显示
   - 交互式 coverage drill-down
   - 历史趋势分析（6 个月）

---

## 八、总结

### 8.1 任务复杂度总览

| Task | 复杂度 | 预计时间 | 关键挑战 | 优先级 |
|------|--------|---------|---------|--------|
| **Task 1: APU 移植** | ⭐⭐⭐⭐ | 10-15天 | DSim 兼容性 | P0 |
| **Task 2: UVM 移植** | ⭐⭐⭐⭐⭐ | 23-30天 | UVM 兼容性, DPI-C | P0 |
| **Task 3: GitHub Actions** | ⭐⭐ | 3-5天 | Cache 优化 | P0 |
| **Task 4: Weekly Regression** | ⭐⭐⭐⭐ | 12-18天 | Runner, License | P0 |
| **Task 5: Public Website** | ⭐⭐⭐ | 10-15天 | 隐私过滤 | P1 |

**总工作量**: **58-83 天** (约 **12-17 周**，考虑 buffer)

---

### 8.2 核心建议

1. **分阶段执行**: 严格按照 Phase 1 → Phase 4 顺序，不要跳跃
2. **尽早获取 license**: DSim/QuestaSim license 是阻塞因素，必须 Week 3 前到位
3. **充分测试**: 每个 phase 结束后充分测试，避免累积技术债
4. **及时沟通**: Weekly status meeting，遇到阻塞立即上报

---

### 8.3 最终评估

**这是一个复杂的、多技术栈的系统工程项目**：
- ✅ **技术上可行**：CVA6 已有良好的基础（Verilator + VCS）
- ⚠️ **时间线紧张**：8-10 周的时间线可行，但没有太多 buffer
- ⚠️ **资源依赖重**：需要硬件、license、权限等多方支持
- ✅ **价值巨大**：为 OpenHW 建立自主可控的 CI 能力

**我的推荐**:
- **接受这个任务**，它对 OpenHW Group 和您的职业发展都很有价值
- **与领导协商时间线**：建议申请 **12 周**（而非 8 周），留出 buffer
- **立即启动 Phase 1**：文档已完成，可以马上开始 Verilator 工作
- **提前申请 license**：这是最大的风险点

---

**报告结束**

*本分析由 Junchao 完成，基于 CVA6 代码库深度分析和行业最佳实践。*
*如有疑问或需要进一步澄清，请随时联系。*
