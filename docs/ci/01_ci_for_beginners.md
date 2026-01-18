# CI 入门指南 (CI for Beginners)

**目标读者**：第一次接触 CI/Regression 系统的验证工程师

**文档版本**：v1.0 (Week 1)

---

## 一、什么是 CI？

### 1.1 CI 的定义

**CI (Continuous Integration，持续集成)** 是一种软件开发实践，开发者频繁地（每天多次）将代码集成到主分支，每次集成都通过自动化的构建和测试来验证，从而尽早发现问题。

在 CPU/SoC 硬件项目（如 CVA6）中，CI 的核心作用是：
- **自动化验证**：每次代码变更后自动运行测试套件
- **快速反馈**：几分钟到几小时内发现 bug（而非几天）
- **质量保障**：确保代码库始终处于可用状态
- **回归检测**：防止新代码破坏已有功能

### 1.2 为什么硬件项目需要 CI？

传统的"手动运行测试"存在问题：
- ❌ **遗漏测试**：工程师可能忘记运行某些测试
- ❌ **环境差异**：不同机器上的结果不一致
- ❌ **时间成本**：手动运行回归需要数小时
- ❌ **质量波动**：依赖个人责任心

CI 系统解决这些问题：
- ✅ **自动触发**：代码 push 或 PR 自动运行测试
- ✅ **环境一致**：使用标准化的 runner 和工具链
- ✅ **并行执行**：多个测试同时运行
- ✅ **强制门禁**：测试不通过无法合并代码

---

## 二、CI 的关键概念

### 2.1 测试分层 (Test Pyramid)

硬件验证中的 CI 通常分为 3 层：

```
           ┌─────────────────┐
           │  Weekly/Monthly │  - 全面回归（6-24小时）
           │   Regression    │  - 随机测试 + Coverage
           │                 │  - 性能基准测试
           └─────────────────┘
                  ▲
         ┌────────┴────────┐
         │  Nightly/Daily  │  - 完整测试套件（2-6小时）
         │   Regression    │  - 所有 riscv-tests
         │                 │  - 架构合规性测试
         └─────────────────┘
                  ▲
         ┌────────┴────────┐
         │   PR-level      │  - 快速验证（5-15分钟）
         │  Smoke Test     │  - 代表性测试子集
         │                 │  - 基本功能检查
         └─────────────────┘
```

#### **Smoke Test（冒烟测试）**
- **目的**：快速验证"CPU 还活着"
- **时间**：5-15 分钟
- **内容**：每种测试类型选 1-2 个代表性测试
- **触发**：每次 PR（Pull Request）提交
- **示例**：
  ```bash
  # 运行 10 个左右的代表性测试
  - rv64ui-p-add      # 基础整数运算
  - rv64mi-p-csr      # CSR 访问
  - rv64ua-p-amoadd   # 原子操作
  - hello_world       # 简单 C 程序
  ```

#### **Nightly/Daily Regression（每日回归）**
- **目的**：全面功能验证
- **时间**：2-6 小时
- **内容**：
  - 所有 riscv-tests (~350 个)
  - RISC-V 架构合规性测试 (~200 个)
  - 基准测试（Dhrystone, CoreMark）
- **触发**：每晚自动运行
- **示例**：
  ```bash
  bash verif/regress/dv-riscv-arch-test.sh  # 架构测试
  bash verif/regress/dv-riscv-tests.sh      # 官方测试
  bash verif/regress/benchmark.sh           # 性能测试
  ```

#### **Weekly Regression（每周回归）**
- **目的**：Coverage closure + 随机测试
- **时间**：6-24 小时
- **内容**：
  - Nightly 的所有内容
  - 随机指令生成测试（riscv-dv，1000+ 次迭代）
  - Code/Functional Coverage 收集
  - Stress 测试
- **触发**：每周末自动运行
- **示例**：
  ```bash
  export cov=1  # 启用覆盖率收集
  bash verif/regress/dv-generated-tests.sh  # 随机测试
  # 生成 Coverage 报告
  ```

### 2.2 Regression（回归测试）

**回归测试**是指重新运行之前通过的测试，以确保新代码没有破坏已有功能。

**为什么需要回归？**
- 硬件 bug 往往隐藏在 corner cases
- 新功能可能影响看似无关的模块（如：添加浮点指令影响中断响应）
- 优化可能引入新 bug

**CVA6 的回归测试包括**：
1. **ISA 测试**：RISC-V 官方指令集测试
2. **架构合规性**：riscv-arch-test（RISC-V International 认证）
3. **随机测试**：riscv-dv 生成的约束随机指令序列
4. **性能基准**：Dhrystone, CoreMark
5. **定制测试**：CVA6 特有的功能（PMP, MMU, Debug 等）

### 2.3 Coverage（覆盖率）

**Code Coverage（代码覆盖率）**：衡量测试执行了多少 RTL 代码

覆盖率类型：
- **Line Coverage**：有多少行代码被执行
- **Branch Coverage**：if/else 的分支是否都覆盖
- **Toggle Coverage**：信号是否翻转（0→1, 1→0）
- **FSM Coverage**：状态机的所有状态和转换

**目标**：CVA6 代码覆盖率目标 >90%（部分模块 >95%）

**Functional Coverage（功能覆盖率）**：衡量测试覆盖了多少功能场景

示例：
```systemverilog
// ISA Coverage: 所有 RV64I 指令都被执行
covergroup instr_cg;
  ADD:  coverpoint (opcode == ADD);
  SUB:  coverpoint (opcode == SUB);
  // ... 所有指令
endgroup

// 寄存器 Hazard Coverage
covergroup hazard_cg;
  rd_eq_rs1:  coverpoint (rd == rs1);  // Write-after-Read
  rd_eq_rs2:  coverpoint (rd == rs2);
  back2back:  coverpoint (instr[n].rd == instr[n+1].rs1);
endgroup
```

**目标**：功能覆盖率 >85%

---

## 三、CVA6 CI 的最小闭环

### 3.1 一个完整的 CI 流程

以 GitHub PR 为例，展示从提交代码到合并的完整流程：

```
Developer                    GitHub                    CI System               Result
   │                            │                          │                      │
   │──1. git push origin PR─────>│                          │                      │
   │                            │                          │                      │
   │                            │──2. Trigger CI──────────>│                      │
   │                            │                          │                      │
   │                            │                          │──3. Checkout Code   │
   │                            │                          │──4. Build Tools     │
   │                            │                          │──5. Run Tests       │
   │                            │                          │                      │
   │                            │<─6. Report Results───────│                      │
   │                            │                          │                      │
   │<─7. See Status on PR───────│                          │                      │
   │                            │                          │                      │
   │──8. Fix Issues (if fail)───>│                          │                      │
   │   (repeat until PASS)      │                          │                      │
   │                            │                          │                      │
   │──9. Merge (after PASS)─────>│                          │                      │
```

### 3.2 最小 CI 示例（5 分钟快速上手）

假设您想在本地模拟 CI 流程：

```bash
# Step 1: 设置环境变量
export RISCV=/path/to/riscv-toolchain  # RISC-V 工具链
export NUM_JOBS=8                       # 并行编译数

# Step 2: 进入 CVA6 仓库
cd /path/to/cva6

# Step 3: 初始化子模块（首次）
git submodule update --init --recursive

# Step 4: 安装工具（首次，约 30 分钟）
source ci/install-prereq.sh        # 安装依赖
bash verif/regress/install-verilator.sh  # Verilator v5.008
bash verif/regress/install-spike.sh      # Spike ISS
bash verif/regress/install-riscv-tests.sh # 测试套件

# Step 5: 设置环境
source verif/sim/setup-env.sh

# Step 6: 运行最小测试（约 10 分钟）
DV_SIMULATORS=veri-testharness,spike \
DV_TARGET=cv64a6_imafdc_sv39 \
bash verif/regress/smoke-tests-cv64a6_imafdc_sv39.sh

# Step 7: 查看结果
tail -50 verif/sim/logfile.log
# 期望看到：
# Test rv64ui-p-add PASSED
# Test rv64mi-p-csr PASSED
# ...
# Regression PASSED: 10/10 tests
```

**如果看到 PASSED**：恭喜！您的环境配置正确，可以开始开发了。

**如果看到 FAILED**：检查以下内容：
1. `$RISCV` 变量是否指向有效的工具链？
2. Verilator 是否成功安装？（检查 `tools/verilator/bin/verilator`）
3. Spike 是否成功编译？（检查 `tools/spike/bin/spike`）

---

## 四、常见 CI 失败类型和排查路径

### 4.1 失败分类决策树

```
CI Job FAILED
    │
    ├─> Build Failed?
    │   ├─> 编译错误 → 检查语法、工具版本
    │   ├─> 缺少文件 → 检查子模块是否更新
    │   └─> 工具崩溃 → 检查内存、磁盘空间
    │
    ├─> Test Failed?
    │   ├─> Timeout → 增加 max_cycles，检查死锁
    │   ├─> Assertion → 查看波形，定位信号
    │   ├─> Mismatch (Spike vs RTL) → 使用 RVFI 对比
    │   └─> Segfault → 检查 testbench 内存访问
    │
    ├─> Environment Failed?
    │   ├─> License 失败 → 检查 license 服务器
    │   ├─> Runner 离线 → 联系基础设施团队
    │   └─> 磁盘满 → 清理临时文件
    │
    └─> Flaky Test?
        ├─> 偶尔失败 → 可能是 race condition
        ├─> 特定 seed 失败 → 使用该 seed 调试
        └─> 不同机器结果不同 → 检查工具版本差异
```

### 4.2 常见错误和解决方案

#### 错误 1: `RISCV variable undefined`
```bash
Error: RISCV variable undefined.
```

**原因**：未设置 RISC-V 工具链路径

**解决**：
```bash
export RISCV=/path/to/riscv-toolchain
# 或者使用 CVA6 推荐的预编译版本
export RISCV=$PWD/tools/riscv-toolchain
```

#### 错误 2: `verilator: command not found`
```bash
bash: verilator: command not found
```

**原因**：Verilator 未安装或未加入 PATH

**解决**：
```bash
# 重新安装
bash verif/regress/install-verilator.sh

# 检查安装
which verilator
# 期望输出：/path/to/cva6/tools/verilator/bin/verilator

# 如果还是找不到，手动加入 PATH
export PATH=$PWD/tools/verilator/bin:$PATH
```

#### 错误 3: `Test TIMEOUT after 10000000 cycles`
```bash
Test rv64mi-p-csr TIMEOUT after 10000000 cycles
```

**原因**：
- 死锁（CPU 卡住不动）
- 测试本身很慢（如大量内存访问）
- `max_cycles` 设置太小

**解决**：
```bash
# 增加超时时间
make sim elf_file=test.elf max_cycles=100000000

# 或在 Python 框架中
python3 cva6.py --test rv64mi-p-csr --sim_opts="+max-cycles=100000000"

# 如果仍然超时，检查是否死锁
# 1. 查看波形（如果启用了 TRACE）
gtkwave trace_hart_0000.vcd
# 2. 查看 PC 是否停止变化
# 3. 检查是否在等待中断或异常
```

#### 错误 4: `Spike/RTL mismatch at PC=0x80000120`
```bash
ERROR: Spike/RTL mismatch
  Spike: x10 = 0x0000000000000042
  RTL:   x10 = 0x0000000000000000
  PC = 0x80000120
```

**原因**：RTL 和 ISS（Spike）执行结果不一致

**解决**：
```bash
# 1. 检查是哪条指令
riscv64-unknown-elf-objdump -d test.elf | grep 80000120
# 输出示例：80000120: 00a58533  add a0, a1, a0

# 2. 查看 RVFI trace（如果启用）
cat verif/sim/trace_hart_0000.log | grep 80000120

# 3. 使用 Spike 单步调试
spike -d test.elf
(spike) until pc 0 0x80000120
(spike) reg 0 a0  # 查看寄存器值

# 4. 查看 CVA6 波形
# 重新运行并生成波形
make verilate TRACE_COMPACT=1
./work-ver/Variane_testharness test.elf
gtkwave trace_hart_0000.fst
```

#### 错误 5: `License checkout failed`
```bash
Error: Could not checkout VCS license
```

**原因**：商业 EDA 工具 license 不可用

**解决**：
```bash
# 检查 license 服务器
echo $LM_LICENSE_FILE  # VCS
echo $CDS_LIC_FILE     # Xcelium
echo $MGLS_LICENSE_FILE # QuestaSim

# 测试 license 服务器
lmstat -a  # 查看所有 license 状态

# 如果 license 服务器正常，检查并发数
lmstat -a | grep -i vcs
# 如果所有 license 都在使用，等待或使用其他仿真器（如 Verilator）
```

---

## 五、PR-level vs Nightly vs Weekly 的区别

### 5.1 对比表

| 特性 | PR-level Smoke | Nightly Regression | Weekly Regression |
|------|----------------|--------------------|--------------------|
| **触发** | 每次 PR 提交 | 每天夜间自动 | 每周末自动 |
| **时间** | 5-15 分钟 | 2-6 小时 | 6-24 小时 |
| **测试数量** | 10-20 个 | 500-600 个 | 1000-1500 个 |
| **仿真器** | Verilator（快） | Verilator + VCS/Questa | VCS/Questa（精确） |
| **Coverage** | 不收集 | 可选 | 必须收集 |
| **随机测试** | 无 | 少量 | 大量（1000+ iter） |
| **目的** | 快速反馈 | 全面功能验证 | Coverage closure |
| **失败影响** | 阻止 PR 合并 | 通知团队修复 | 高优先级修复 |

### 5.2 何时运行哪种测试？

**场景 1：修复一个小 bug（如：ALU 加法进位错误）**
```bash
# 1. 本地运行相关测试
DV_SIMULATORS=veri-testharness \
DV_TARGET=cv64a6_imafdc_sv39 \
python3 verif/sim/cva6.py --test rv64ui-p-add

# 2. 提交 PR → 自动触发 smoke test（15 分钟）
# 3. 如果 PASS，合并代码
# 4. 当晚的 nightly regression 会再次验证（2 小时）
```

**场景 2：添加新指令扩展（如：添加 Zba 扩展）**
```bash
# 1. 本地运行完整的 ISA 测试
bash verif/regress/dv-riscv-tests.sh

# 2. 提交 PR → smoke test（必须 PASS）
# 3. 手动触发 nightly regression（等待结果）
# 4. 合并后，weekly regression 会检查 coverage
```

**场景 3：性能优化（如：优化分支预测器）**
```bash
# 1. 运行 smoke test（确保功能正确）
bash verif/regress/smoke-tests-cv64a6_imafdc_sv39.sh

# 2. 运行性能基准测试
bash verif/regress/coremark.sh
bash verif/regress/dhrystone.sh

# 3. 对比优化前后的性能数据
# 4. 提交 PR → 等待 nightly regression 确认没有破坏功能
```

---

## 六、CVA6 特定的 CI 术语

### 6.1 目标配置 (Target Configuration)

CVA6 支持多种硬件配置，通过 `DV_TARGET` 环境变量选择：

| 配置名 | 位宽 | ISA 扩展 | MMU | 用途 |
|--------|------|---------|-----|------|
| `cv64a6_imafdc_sv39` | 64 | IMAFDC | Sv39 | 默认 64 位配置 |
| `cv64a6_imafdc_sv39_hpdcache` | 64 | IMAFDC | Sv39 | 使用高性能 D-Cache |
| `cv32a65x` | 32 | IMAFC | Sv32 | 32 位应用级 |
| `cv32a60x` | 32 | IMC | Sv32 | 32 位嵌入式 |
| `cv32a6_imac_sv0` | 32 | IMAC | 无 | 无 MMU 配置 |

**示例**：
```bash
# 运行 64 位配置的测试
export DV_TARGET=cv64a6_imafdc_sv39

# 运行 32 位配置的测试
export DV_TARGET=cv32a65x
```

### 6.2 仿真器 (Simulator)

CVA6 支持多种仿真器，通过 `DV_SIMULATORS` 环境变量选择：

| 仿真器 | 类型 | 速度 | 精度 | License | CI 使用 |
|--------|------|------|------|---------|---------|
| `veri-testharness` | 开源 | 最快 | 高 | 免费 | ✅ PR-level |
| `spike` | ISS | 极快 | 参考 | 免费 | ✅ Tandem 模式 |
| `vcs-testharness` | 商业 | 快 | 最高 | 需要 | Nightly |
| `vcs-uvm` | 商业 | 中 | 最高 | 需要 | Weekly |
| `questa-testharness` | 商业 | 快 | 最高 | 需要 | Nightly |
| `questa-uvm` | 商业 | 中 | 最高 | 需要 | Weekly |

**Tandem 模式**：同时运行 RTL 仿真器和 ISS（Spike），每条指令执行后对比结果
```bash
export SPIKE_TANDEM=1
DV_SIMULATORS=veri-testharness,spike \
bash verif/regress/smoke-tests-cv64a6_imafdc_sv39.sh
```

### 6.3 Testbench 类型

CVA6 有两种 testbench：

#### **APU Testbench**（简化版）
- **位置**：`verif/tb/core/`
- **用途**：快速功能验证
- **特点**：
  - 轻量级，编译快
  - 直接加载 ELF 到内存
  - 支持 Verilator, VCS, Questa, Xcelium
  - 适合 smoke test 和 directed test

#### **UVM Testbench**（完整版）
- **位置**：`verif/tb/uvmt/`
- **用途**：深度验证和 coverage closure
- **特点**：
  - 完整的 UVM 环境
  - 支持约束随机测试
  - Functional coverage
  - 协议检查器（AXI, CVXIF）
  - 仅支持商业仿真器（VCS, Questa, Xcelium）

**选择建议**：
- 开发阶段：使用 APU testbench + Verilator（快速迭代）
- PR 验证：使用 APU testbench + smoke test
- Regression：使用 UVM testbench + 随机测试 + coverage

---

## 七、实用命令速查

### 7.1 环境设置

```bash
# 设置工具链
export RISCV=/path/to/riscv-toolchain
export NUM_JOBS=8  # 并行编译数

# 设置目标配置
export DV_TARGET=cv64a6_imafdc_sv39

# 设置仿真器
export DV_SIMULATORS=veri-testharness,spike

# 加载环境配置
source verif/sim/setup-env.sh
```

### 7.2 运行测试

```bash
# Smoke test（快速验证）
bash verif/regress/smoke-tests-cv64a6_imafdc_sv39.sh

# 单个测试
cd verif/sim
python3 cva6.py \
  --target cv64a6_imafdc_sv39 \
  --iss veri-testharness,spike \
  --iss_yaml cva6.yaml \
  --test rv64ui-p-add

# 运行整个 testlist
python3 cva6.py \
  --target cv64a6_imafdc_sv39 \
  --iss veri-testharness,spike \
  --testlist ../tests/testlist_riscv-tests-cv64a6_imafdc_sv39-v.yaml

# 使用 Makefile
cd verif/sim
make veri-testharness target=cv64a6_imafdc_sv39 elf=test.elf
```

### 7.3 查看结果

```bash
# 查看测试日志
tail -100 verif/sim/logfile.log

# 查看单个测试的详细日志
ls verif/sim/out_*/veri-testharness_sim/
cat verif/sim/out_*/veri-testharness_sim/rv64ui-p-add.log

# 查看波形（如果启用 TRACE_COMPACT）
gtkwave verif/sim/trace_hart_0000.fst
```

### 7.4 清理环境

```bash
# 清理仿真结果
cd verif/sim
make clean_all

# 清理特定仿真器的结果
make vcs_clean_all
rm -rf questa_results/

# 完全清理（包括工具链，谨慎使用）
rm -rf tools/
rm -rf tmp/
```

---

## 八、下一步学习

阅读完本文档后，您应该：
1. ✅ 理解 CI 的基本概念和分层
2. ✅ 知道 smoke test、nightly、weekly 的区别
3. ✅ 能够在本地运行最小 CI 示例
4. ✅ 会排查常见的 CI 失败

**继续学习**：
- 📖 [`02_current_cva6_ci_inventory.md`](./02_current_cva6_ci_inventory.md) - 了解 CVA6 当前的 CI 系统
- 📖 [`03_how_ci_runs_end_to_end.md`](./03_how_ci_runs_end_to_end.md) - 深入理解 CI 执行流程
- 📖 [`07_test_and_regression_strategy.md`](./07_test_and_regression_strategy.md) - 测试策略和最佳实践

**实践任务**：
1. 在本地运行 smoke test（参考第三节）
2. 故意引入一个 bug（如修改 ALU），观察 CI 如何发现
3. 查看 GitHub Actions 的 workflow 文件（`.github/workflows/ci.yml`）

---

## 九、FAQ（常见问题）

**Q1: 我修改了代码，但本地测试通过，CI 却失败了？**

A: 可能的原因：
- 工具版本不同（本地 Verilator 4.x，CI 使用 5.x）
- 环境变量差异（$RISCV 路径不同）
- 测试集不同（本地运行部分测试，CI 运行全部）

**解决**：使用 CI 相同的工具版本和环境配置。

---

**Q2: 如何在不提交 PR 的情况下测试 CI？**

A:
```bash
# 方法 1: 在本地完全模拟 CI
source ci/setup.sh  # GitHub Actions 使用的安装脚本
bash verif/regress/smoke-tests-cv64a6_imafdc_sv39.sh

# 方法 2: 使用 act 工具（本地运行 GitHub Actions）
# https://github.com/nektos/act
act pull_request
```

---

**Q3: CI 运行太慢，如何加速？**

A:
- PR-level：仅运行 smoke test（已经很快，15 分钟）
- 使用 cache（toolchain, verilator, spike）
- 并行运行测试（`NUM_JOBS=16`）
- 使用更快的仿真器（Verilator > VCS > Questa）

---

**Q4: 如何添加新的测试到 CI？**

A: 参考 [`07_test_and_regression_strategy.md`](./07_test_and_regression_strategy.md) 中的"添加测试流程"。

---

**文档维护**：如有问题或建议，请在 CVA6 仓库提 issue 或联系 CI 维护者。

**版本历史**：
- v1.0 (2026-01-17): 初始版本
