# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

CVA6 是一个 6 级、单发射、按序执行的 64 位 RISC-V CPU 核心，完整实现了 I、M、A、C 扩展以及特权架构。支持 M、S、U 三种特权级别，可运行完整的类 Unix 操作系统。

## 目录结构

```
core/               # CVA6 核心处理器 RTL 代码（仅核心，不依赖 APU）
  ├── cva6.sv                # 顶层模块
  ├── frontend/              # 取指前端（分支预测、指令队列）
  ├── cache_subsystem/       # 缓存子系统（ICache、DCache、HPDCache）
  ├── cva6_mmu/             # 内存管理单元（TLB、PTW）
  ├── include/              # 配置包和类型定义（15 个配置）
  └── [其他流水线模块]

corev_apu/          # CVA6 APU FPGA 仿真平台（依赖 core/）
  ├── tb/                   # APU 级测试平台
  ├── fpga/                 # FPGA 实现（Xilinx、Altera）
  └── src/                  # APU 源代码

verif/              # 验证环境
  ├── sim/                  # 仿真环境（Makefile、Python 脚本）
  ├── tb/core/             # CVA6 核心测试平台
  ├── bsp/                  # 板级支持包（链接脚本）
  ├── tests/                # 测试用例和测试列表
  ├── regress/              # 回归和工具安装脚本
  └── core-v-verif/         # 共享验证组件（子模块）

config/             # 配置生成脚本（riscv-config）
vendor/             # 第三方 IP（AXI、PULP 组件）
docs/               # 文档（Sphinx）
tutorials/          # 教程（运行仿真、ASIC、FPGA）
```

## 常用命令

### 环境设置

```bash
# 必需环境变量
export RISCV=/path/to/riscv-toolchain      # RISC-V 工具链根目录
export NUM_JOBS=4                           # 并行编译线程数（推荐不超过 CPU 核心数的 2/3）

# 可选环境变量
export DV_SIMULATORS=veri-testharness,spike # 仿真器选择
export SPIKE_INSTALL_DIR=$PWD/tools/spike   # Spike 安装路径
export VERILATOR_INSTALL_DIR=$PWD/tools/verilator
```

### 一次性初始化

```bash
# 安装 GCC 工具链（强烈推荐使用仓库提供的脚本）
cd util/toolchain-builder
# 查看 README.md 了解前置依赖和构建步骤

# 安装 Verilator、Spike 和测试套件
export DV_SIMULATORS=veri-testharness,spike
bash verif/regress/smoke-tests.sh
```

### 构建和仿真（顶层 Makefile）

```bash
# 使用 QuestaSim 构建
make build target=cv64a6_imafdc_sv39

# 使用 Verilator 构建
make verilate target=cv64a6_imafdc_sv39

# 运行单个测试（QuestaSim）
make sim elf_file=path/to/test.elf

# 运行单个测试（Verilator）
make sim-verilator elf_file=path/to/test.elf

# 运行 RISC-V ISA 测试
make run-asm-tests target=cv64a6_imafdc_sv39
make run-benchmarks

# 清理构建
make clean
```

### Python 测试框架（verif/sim/）

这是推荐的测试执行方式。

```bash
cd verif/sim

# 初始化环境
source setup-env.sh

# 运行单个测试
python3 cva6.py \
  --target cv64a6_imafdc_sv39 \
  --iss veri-testharness,spike \
  --iss_yaml cva6.yaml \
  --testlist ../tests/testlist_riscv-tests-cv64a6_imafdc_sv39-v.yaml \
  --test rv64ui-v-add

# 运行测试列表
python3 cva6.py \
  --target cv64a6_imafdc_sv39 \
  --iss $DV_SIMULATORS \
  --testlist ../tests/testlist_riscv-compliance-cv64a6_imafdc_sv39.yaml

# 运行覆盖率
python3 cva6.py --target cv64a6_imafdc_sv39 --iss vcs-uvm --cov

# 清理
make clean_all
```

### 回归测试脚本（verif/regress/）

```bash
# 快速烟雾测试（推荐首次验证）
bash verif/regress/smoke-tests-cv64a6_imafdc_sv39.sh

# 基准测试（Dhrystone、CoreMark）
bash verif/regress/dhrystone.sh
bash verif/regress/coremark.sh

# 完整回归
bash verif/regress/cv64a6_imafdc_tests.sh
```

## 硬件配置系统

### 支持的配置（target 参数）

CVA6 使用参数化设计支持多种配置：

**64 位配置：**
- `cv64a6_imafdc_sv39` - 默认 64 位配置（完整浮点、Sv39 MMU）
- `cv64a6_imafdcv_sv39` - 包含向量扩展
- `cv64a6_imafdc_sv39_hpdcache` - 使用高性能 D 缓存
- `cv64a6_imafdc_sv39_wb` - 写回缓存

**32 位配置：**
- `cv32a60x` - 32 位嵌入式（无浮点）
- `cv32a65x` - 32 位应用级
- `cv32a6_imac_sv0` - 无 MMU
- `cv32a6_imac_sv32` - Sv32 MMU
- `cv32a6_imafc_sv32` - 浮点 + Sv32 MMU

### 配置文件位置

配置包定义在 `core/include/`:
- `config_pkg.sv` - 基础配置包类型定义
- `cv64a6_imafdc_sv39_config_pkg.sv` - 特定配置包（每个 target 一个）
- `build_config_pkg.sv` - 构建时合并配置

关键配置参数：
- `XLEN` - 32 或 64 位
- `RVA/RVB/RVC/RVD/RVF/RVH/RVV` - ISA 扩展开关
- `DCACHE_TYPE` - 缓存类型（WB/WT/HPDCACHE_WB/HPDCACHE_WT）
- `BPREDICTOR` - 分支预测器类型（BHT/PH_BHT）
- MMU 模式（Sv32/Sv39/Sv48）

## 核心架构

CVA6 是一个 **6 级流水线**：

1. **IF（Instruction Fetch）** - 取指
   - 模块：`frontend/frontend.sv`
   - 分支预测：BTB、BHT、RAS

2. **ID（Instruction Decode）** - 解码
   - 模块：`id_stage.sv`、`decoder.sv`
   - 寄存器读取、记分板检查

3. **ISSUE** - 发射
   - 模块：`issue_stage.sv`、`scoreboard.sv`

4. **EX（Execute）** - 执行
   - 模块：`ex_stage.sv`
   - 执行单元：`alu.sv`、`mult.sv`、`fpu_wrap.sv`、`branch_unit.sv`

5. **MEM（Memory）** - 访存
   - 模块：`load_store_unit.sv`、`load_unit.sv`、`store_unit.sv`

6. **WB/COMMIT（Write Back/Commit）** - 写回/提交
   - 模块：`commit_stage.sv`

**缓存子系统：**
- 指令缓存（`cache_subsystem/std_cache_subsystem.sv`）
- 数据缓存（支持多种类型）
- HPDCache（高性能数据缓存，`core/cache_subsystem/hpdcache/`）

**MMU：**
- TLB（Translation Lookaside Buffer）
- PTW（Page Table Walker）
- PMP（Physical Memory Protection）

## 验证环境

### 测试类型

1. **riscv-tests** - RISC-V 官方 ISA 测试
   - 位置：`tmp/riscv-tests/`（通过安装脚本下载）
   - 测试列表：`verif/tests/testlist_riscv-tests-*.yaml`

2. **riscv-compliance** - RISC-V 兼容性测试
   - 测试列表：`verif/tests/testlist_riscv-compliance-*.yaml`

3. **riscv-arch-test** - RISC-V 架构测试
   - 测试列表：`verif/tests/testlist_riscv-arch-test-*.yaml`

4. **riscv-dv** - 随机指令生成
   - 位置：`verif/sim/dv/`
   - 配置：`verif/sim/cva6.py`

5. **Custom tests** - 自定义测试
   - 位置：`verif/tests/custom/`

### 仿真器支持

- **Verilator** - 开源，快速，推荐日常开发
- **Spike** - RISC-V ISA 参考模型（用于对比）
- **VCS** - Synopsys 商业仿真器
- **QuestaSim** - Mentor 商业仿真器
- **Xcelium** - Cadence 商业仿真器

通过 `DV_SIMULATORS` 环境变量选择：
```bash
DV_SIMULATORS=veri-testharness,spike  # Verilator + Spike（推荐）
DV_SIMULATORS=vcs-testharness,spike   # VCS + Spike
```

## 贡献指南要点

1. **新功能要求：**
   - 提前与团队沟通（info@openhwgroup.org 或 GitHub issue）
   - 默认禁用，通过 SystemVerilog 参数控制
   - 承诺 2 年维护期
   - 必须通过 CI 流程

2. **代码规范：**
   - `core/` 目录下的 RTL 使用 `verible-verilog-format` 格式化
   - DRY 原则（不重复代码）
   - 需签署 Eclipse Contributor Agreement

3. **代码格式化：**
   ```bash
   # 格式化单个文件
   verible-verilog-format --inplace core/path/to/file.sv

   # 格式化整个目录
   util/format-verible
   ```

4. **PR 流程：**
   - 可以标记 "do not merge" 来测试 CI
   - 所有代码覆盖率不能降低
   - 需提供回归测试

## FPGA 实现

### Xilinx FPGA

```bash
# 支持的板子：genesys2, kc705, vc707, nexys_video
make fpga BOARD=genesys2 target=cv64a6_imafdc_sv39
```

构建产物：`corev_apu/fpga/work-fpga/`

### Altera/Intel FPGA

```bash
make altera ALTERA_BOARD=DK-DEV-AGF014E3ES target=cv64a6_imafdc_sv39
```

## 调试和追踪

### Verilator 波形追踪

```bash
# 快速追踪（VCD）
make verilate TRACE_FAST=1
./work-ver/Variane_testharness test.elf

# 紧凑追踪（FST，推荐）
make verilate TRACE_COMPACT=1
./work-ver/Variane_testharness test.elf
```

波形文件：`trace_hart_*.vcd` 或 `trace_hart_*.fst`

### 指令追踪

启用后生成详细的指令执行日志：
- `trace_hart_0000.log` - 指令追踪日志
- `trace_hart_0000_commit.log` - 提交阶段日志

查看：
```bash
less trace_hart_0000.log
```

### Spike Tandem 模式

与 Spike 参考模型并行运行，逐周期对比：
```bash
export SPIKE_TANDEM=1
make build target=cv64a6_imafdc_sv39
make sim elf_file=test.elf
```

## 性能分析

CVA6 包含性能模型（`perf-model/`）用于微架构性能评估。

运行基准测试：
```bash
bash verif/regress/benchmark.sh    # Dhrystone 等基准
bash verif/regress/coremark.sh     # CoreMark 基准
```

## 常见问题排查

### 构建失败

1. **检查环境变量：**
   ```bash
   echo $RISCV
   echo $VERILATOR_INSTALL_DIR
   echo $SPIKE_INSTALL_DIR
   ```

2. **重新安装工具：**
   ```bash
   bash verif/regress/install-verilator.sh
   bash verif/regress/install-spike.sh
   ```

3. **清理构建：**
   ```bash
   make clean
   cd verif/sim && make clean_all
   ```

### 仿真失败

1. **检查 ELF 文件路径**
2. **查看日志：**
   - Verilator：标准输出
   - QuestaSim：`transcript` 文件
3. **启用调试追踪：**
   ```bash
   make verilate TRACE_COMPACT=1 DEBUG=1
   ```

### 测试超时

调整最大周期数：
```bash
make sim elf_file=test.elf max_cycles=100000000
```

或在 Python 脚本中：
```bash
python3 cva6.py --test mytest --sim_opts="+max-cycles=100000000"
```

## 参考文档

- **用户手册：** https://docs.openhwgroup.org/projects/cva6-user-manual/
- **GitHub：** https://github.com/openhwgroup/cva6
- **运行仿真教程：** `tutorials/running_sim.md`
- **FPGA 实现教程：** `tutorials/fpga.md`
- **ASIC 实现教程：** `tutorials/asic.md`
- **贡献指南：** `CONTRIBUTING.md`
- **资源生态：** `RESOURCES.md`

## 技术栈

- **RTL：** SystemVerilog
- **仿真：** Verilator、VCS、QuestaSim、Xcelium
- **验证：** UVM、riscv-dv、Spike
- **构建：** Make、Python 3、Bender
- **工具链：** RISC-V GCC/LLVM
- **文档：** Sphinx（reStructuredText）
