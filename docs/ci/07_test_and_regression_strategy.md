# 测试和回归策略（Test and Regression Strategy）

**文档版本**: v1.0
**创建日期**: 2026-01-18
**维护者**: OpenHW CI Team
**目标读者**: 验证工程师、CI 维护者、测试开发者

---

## 文档目的

本文档定义 **CVA6 的测试和回归验证策略**，包括：
- 🎯 测试分层原则
- 📊 Coverage 目标和收集方法
- 📝 Testlist 维护规范
- 🔄 Regression 运行策略

---

## 目录

1. [测试分层策略](#一测试分层策略)
2. [测试套件组织](#二测试套件组织)
3. [Coverage 策略](#三coverage-策略)
4. [Regression 运行策略](#四regression-运行策略)
5. [测试选择原则](#五测试选择原则)
6. [Testlist 维护规范](#六testlist-维护规范)
7. [测试质量指标](#七测试质量指标)

---

## 一、测试分层策略

### 1.1 测试金字塔（Test Pyramid）

CVA6 采用 **三层测试金字塔** 结构：

```
           ┌──────────────┐
           │  Weekly      │  Coverage >90%, 所有测试
           │  (1200+ tests│  Runtime: 8-12 hr
           │   6-12 hr)   │  Trigger: 每周日 00:00
           └──────────────┘
               ▲
               │
          ┌────────────────┐
          │   Nightly      │   Coverage >80%, 核心测试
          │  (800 tests    │   Runtime: 4-6 hr
          │    4-6 hr)     │   Trigger: 每天 00:00
          └────────────────┘
              ▲
              │
         ┌─────────────────┐
         │  PR Smoke        │    Coverage >60%, 快速验证
         │  (50-100 tests   │    Runtime: 20-30 min
         │   20-30 min)     │    Trigger: 每个 PR
         └─────────────────┘
```

---

### 1.2 分层详细定义

#### Level 1: PR Smoke Test（冒烟测试）

**目标**: 快速验证基础功能，阻止明显错误进入主分支

| 属性 | 值 |
|------|-----|
| **测试数量** | 50-100 |
| **运行时间** | 20-30 分钟 |
| **触发频率** | 每个 PR |
| **仿真器** | Verilator + Spike |
| **Coverage 目标** | >60% line coverage |
| **失败阈值** | 0 failures (100% must pass) |

**包含的测试**:
- ✅ 基础 ISA 测试 (rv64ui-p-add, sub, and, or, xor, ...)
- ✅ Load/Store 测试 (lw, sw, ld, sd)
- ✅ Branch 测试 (beq, bne, blt, bge)
- ✅ 特权指令 (ecall, mret)
- ✅ Custom 测试 (hello_world.c)

**示例 Testlist**: `verif/tests/testlist_riscv-tests-cv64a6_imafdc_sv39-p-smoke.yaml`

---

#### Level 2: Nightly Regression（每晚回归）

**目标**: 覆盖大部分功能，发现常见回归问题

| 属性 | 值 |
|------|-----|
| **测试数量** | 700-900 |
| **运行时间** | 4-6 小时 |
| **触发频率** | 每天 00:00 (UTC+8) |
| **仿真器** | VCS/Questa + Spike |
| **Coverage 目标** | >80% line, >75% branch |
| **失败阈值** | <5% failures |

**包含的测试**:
- ✅ 完整 rv64i/m/a/f/d/c 测试
- ✅ riscv-arch-test 全集
- ✅ 特权模式测试 (rv64si, rv64mi)
- ✅ PMP 测试
- ✅ 虚拟内存测试 (Sv39)
- ⏳ Benchmark (CoreMark, Dhrystone)

**示例 Testlist**: `verif/tests/testlist_riscv-tests-cv64a6_imafdc_sv39-p.yaml`

---

#### Level 3: Weekly Full Regression（每周完整回归）

**目标**: 最大化覆盖率，发现 corner case bugs

| 属性 | 值 |
|------|-----|
| **测试数量** | 1200+ |
| **运行时间** | 8-12 小时 |
| **触发频率** | 每周日 00:00 (UTC+8) |
| **仿真器** | VCS + Spike（启用 Coverage）|
| **Coverage 目标** | >90% line, >85% branch, >95% FSM |
| **失败阈值** | <3% failures |

**包含的测试**:
- ✅ Nightly 所有测试
- ✅ riscv-dv 随机测试 (500+ random programs)
- ✅ UVM 随机测试 (200+ constrained random)
- ✅ Stress tests (长时间运行测试)
- ✅ Multi-core tests (如果支持)
- ✅ CVXIF (CV-X-IF) 扩展测试

**示例 Testlist**: 所有 testlist 的并集

---

### 1.3 分层对比表

| 维度 | PR Smoke | Nightly | Weekly |
|------|----------|---------|--------|
| **测试数量** | 50-100 | 700-900 | 1200+ |
| **运行时间** | 20-30 min | 4-6 hr | 8-12 hr |
| **仿真器** | Verilator | VCS/Questa | VCS + Cov |
| **Line Coverage** | >60% | >80% | >90% |
| **Branch Coverage** | >50% | >75% | >85% |
| **FSM Coverage** | N/A | N/A | >95% |
| **Functional Cov** | N/A | N/A | >70% |
| **失败阈值** | 0% | <5% | <3% |
| **阻塞 PR merge** | ✅ Yes | ❌ No | ❌ No |

---

## 二、测试套件组织

### 2.1 测试套件分类

CVA6 使用以下测试套件：

#### 1. riscv-tests（官方 ISA 测试）

**来源**: https://github.com/riscv/riscv-tests

**覆盖范围**:
- RV64I: 基础整数指令
- RV64M: 乘除法扩展
- RV64A: 原子操作扩展
- RV64F: 单精度浮点
- RV64D: 双精度浮点
- RV64C: 压缩指令
- Privileged: 特权级指令（S-mode, M-mode）

**测试格式**:
- `-p-` 后缀: Physical address mode
- `-v-` 后缀: Virtual address mode (Sv39)

**示例测试**:
```
rv64ui-p-add        # User-mode Integer, Physical, ADD instruction
rv64um-v-mul        # User-mode Multiply, Virtual, MUL instruction
rv64ua-p-amoadd_w   # User-mode Atomic, Physical, AMOADD.W instruction
rv64si-p-csr        # Supervisor-mode, Physical, CSR access
```

---

#### 2. riscv-arch-test（架构合规测试）

**来源**: https://github.com/riscv-non-isa/riscv-arch-test

**覆盖范围**:
- 所有 RISC-V 扩展的合规性
- 更严格的 corner case 测试
- 官方认证测试集

**测试数量**: ~500 tests

**示例 Testlist**: `testlist_riscv-arch-test-cv64a6_imafdc_sv39.yaml`

---

#### 3. riscv-dv（随机测试生成器）

**来源**: https://github.com/chipsalliance/riscv-dv

**特点**:
- 基于 UVM 的随机指令生成
- 可配置约束（指令类型、地址范围、异常触发）
- 自动生成 self-checking 测试

**使用场景**:
- Weekly regression（生成 500+ 随机程序）
- Coverage closure（针对性生成覆盖未达的场景）

**示例配置**:
```yaml
# riscv-dv.yaml
num_of_tests: 500
num_of_iterations: 1000
enable_interrupt: true
enable_exception: true
enable_fp: true
enable_compressed: true
```

---

#### 4. Custom Tests（CVA6 定制测试）

**来源**: `verif/tests/custom/`

**类型**:
- **功能测试**: 测试特定 CVA6 功能（PMP, CVXIF, HPDCache）
- **Benchmark**: CoreMark, Dhrystone, Embench
- **Bug 回归测试**: 每个修复的 bug 对应一个测试

**示例**:
```
custom/pmp/pmp_basic.S          # PMP 基础测试
custom/cvxif/cvxif_add.S        # CVXIF 扩展测试
custom/hello_world/hello_world.c # C 语言编译测试
custom/coremark/              # CoreMark benchmark
```

---

### 2.2 Testlist 文件组织

所有测试通过 **YAML testlist** 文件组织：

```
verif/tests/
├── testlist_riscv-tests-cv64a6_imafdc_sv39-p.yaml       # RV64 physical mode
├── testlist_riscv-tests-cv64a6_imafdc_sv39-v.yaml       # RV64 virtual mode
├── testlist_riscv-arch-test-cv64a6_imafdc_sv39.yaml     # Arch test
├── testlist_riscv-compliance-cv64a6_imafdc_sv39.yaml    # Compliance
├── testlist_custom.yaml                                  # Custom tests
└── testlist_smoke.yaml                                   # Smoke test subset
```

#### Testlist 格式示例

```yaml
# testlist_smoke.yaml

name: "CVA6 Smoke Test Suite"
description: "Fast sanity check for PR-level CI"

tests:
  - test: rv64ui-p-add
    iterations: 1
    rtl_test: true
    iss: spike
    timeout: 60

  - test: rv64ui-p-sub
    iterations: 1
    rtl_test: true
    iss: spike
    timeout: 60

  - test: rv64um-p-mul
    iterations: 1
    rtl_test: true
    iss: spike
    timeout: 120  # Mul/Div 测试可能更慢
```

---

## 三、Coverage 策略

### 3.1 Coverage 类型和目标

CVA6 收集以下类型的 coverage：

| Coverage 类型 | 定义 | 当前值 | 目标值 | 优先级 |
|--------------|------|--------|--------|--------|
| **Line Coverage** | 代码行执行率 | 92% | 95% | P1 |
| **Branch Coverage** | 分支覆盖率 | 88% | 90% | P1 |
| **FSM Coverage** | 状态机状态覆盖 | 95% | 98% | P2 |
| **Toggle Coverage** | 信号翻转覆盖 | 85% | N/A | P3 |
| **Functional Coverage** | 功能点覆盖 | 70% | 85% | P1 |

---

### 3.2 Code Coverage 收集方法

#### VCS Coverage

```makefile
# verif/sim/Makefile

vcs-testharness-cov:
    vcs +define+CV_VP_DEBUG_LOG \
        -cm line+cond+fsm+tgl+branch \
        -cm_dir vcs_results/coverage.vdb \
        -sverilog \
        ...
```

#### Questa Coverage

```makefile
questa-testharness-cov:
    vopt +cover=bcesf \
        -o optimized_design \
        ...
    vsim -coverage \
        -do "coverage save -onexit coverage.ucdb" \
        ...
```

---

### 3.3 Coverage 合并和报告

#### 合并 Coverage Database

```bash
# VCS
urg -dir vcs_results/**/*.vdb \
    -format both \
    -report coverage_report

# Questa
vcover merge -out merged.ucdb \
    test1.ucdb test2.ucdb test3.ucdb ...
vcover report -html -htmldir cov_html merged.ucdb
```

#### Coverage 报告内容

生成的 HTML 报告包含：
- **Summary**: 总体 coverage 百分比
- **File view**: 每个文件的 coverage
- **Line view**: 源码级 coverage（绿色=执行，红色=未执行）
- **Exclusion**: 排除的代码（unreachable code, debug only）

---

### 3.4 Functional Coverage 定义

使用 SystemVerilog Covergroup 定义功能覆盖点：

```systemverilog
// verif/tb/core/cva6_tb_wrapper.sv

covergroup cg_instructions @(posedge clk);
  option.per_instance = 1;

  // 指令类型覆盖
  cp_opcode: coverpoint instr_opcode {
    bins ALU_OPS    = {OPCODE_OP, OPCODE_OP_IMM};
    bins LOAD_OPS   = {OPCODE_LOAD};
    bins STORE_OPS  = {OPCODE_STORE};
    bins BRANCH_OPS = {OPCODE_BRANCH};
    bins JAL_OPS    = {OPCODE_JAL, OPCODE_JALR};
    bins SYSTEM_OPS = {OPCODE_SYSTEM};
  }

  // ALU 运算类型
  cp_alu_op: coverpoint alu_operator iff (instr_opcode == OPCODE_OP) {
    bins ADD = {ALU_ADD};
    bins SUB = {ALU_SUB};
    bins AND = {ALU_AND};
    bins OR  = {ALU_OR};
    bins XOR = {ALU_XOR};
    bins SLL = {ALU_SLL};
    bins SRL = {ALU_SRL};
    bins SRA = {ALU_SRA};
  }

  // Load/Store 大小
  cp_ls_size: coverpoint ls_size iff (instr_opcode inside {OPCODE_LOAD, OPCODE_STORE}) {
    bins BYTE     = {2'b00};
    bins HALFWORD = {2'b01};
    bins WORD     = {2'b10};
    bins DWORD    = {2'b11};
  }

  // 交叉覆盖: Load 类型 × 大小
  cross cp_opcode, cp_ls_size {
    ignore_bins not_load_store = binsof(cp_opcode) intersect {!OPCODE_LOAD, !OPCODE_STORE};
  }
endgroup
```

---

## 四、Regression 运行策略

### 4.1 Regression 时间表

| Regression | 触发时间 | 运行平台 | 责任人 |
|------------|----------|----------|--------|
| **PR Smoke** | 每个 PR push | GitHub Actions | 自动 |
| **Nightly** | 每天 00:00 UTC+8 | GitLab CI (self-hosted) | CI 维护者 |
| **Weekly** | 每周日 00:00 UTC+8 | GitLab CI (self-hosted) | CI 维护者 |
| **Pre-release** | Release 前手动触发 | GitLab CI | Release Manager |

---

### 4.2 Regression 配置差异

#### PR Smoke Test

```yaml
# .github/workflows/ci.yml

env:
  DV_SIMULATORS: veri-testharness,spike
  DV_TARGET: cv64a6_imafdc_sv39
  TESTLIST: testlist_smoke.yaml
  COVERAGE: false  # 不收集 coverage
  TRACE: false     # 不生成波形
```

#### Nightly Regression

```yaml
# .gitlab-ci.yml (nightly job)

variables:
  DV_SIMULATORS: vcs-testharness,spike
  DV_TARGET: cv64a6_imafdc_sv39
  TESTLIST: testlist_riscv-tests-cv64a6_imafdc_sv39-p.yaml,testlist_riscv-arch-test-cv64a6_imafdc_sv39.yaml
  COVERAGE: false  # Nightly 不收集 coverage（节省时间）
  TRACE: false
```

#### Weekly Regression

```yaml
# .gitlab-ci.yml (weekly job)

variables:
  DV_SIMULATORS: vcs-testharness
  DV_TARGET: cv64a6_imafdc_sv39
  TESTLIST: ALL  # 所有 testlist
  COVERAGE: true   # ✅ 收集 coverage
  TRACE: false     # 不生成波形（太大）
  RANDOM_TESTS: 500  # riscv-dv 随机测试数量
```

---

### 4.3 Regression 失败处理

#### 失败率阈值

| Regression | 允许失败率 | 超过阈值时 |
|------------|-----------|-----------|
| **PR Smoke** | 0% | ❌ 阻塞 PR merge |
| **Nightly** | <5% | ⚠️ 告警邮件 |
| **Weekly** | <3% | ⚠️ 告警邮件 + Issue |

#### Known Failures 管理

维护 `known_failures.yaml` 列表：

```yaml
# verif/regress/known_failures.yaml

- test: rv64ua-p-amoadd_w
  platforms: [vcs, questa]
  status: flaky
  reason: "Timing issue, passes 80% of the time"
  jira: CVA6-1234
  expected_fix: "2026-Q2"

- test: rv64mi-p-sbreak
  platforms: [all]
  status: expected_fail
  reason: "Debug extension not implemented"
  jira: N/A
  expected_fix: "TBD"
```

**处理逻辑**:
- ✅ Known failures 不导致 regression FAIL
- ⚠️ Known failures 突然 PASS → 通知 CI 维护者
- ❌ 新的 failures → 导致 regression FAIL

---

## 五、测试选择原则

### 5.1 何时添加新测试

| 场景 | 是否需要测试 | 测试类型 |
|------|-------------|---------|
| **新功能开发** | ✅ 必须 | Directed test + Random test |
| **Bug 修复** | ✅ 必须 | Regression test (复现 bug) |
| **性能优化** | ⏳ 建议 | Benchmark |
| **代码重构** | ❌ 不需要 | （现有测试覆盖）|
| **文档更新** | ❌ 不需要 | N/A |

---

### 5.2 测试编写原则

#### FIRST 原则

- **F**ast: 测试应该快速运行（<1 分钟）
- **I**solated: 测试之间相互独立
- **R**epeatable: 可重复运行，结果一致
- **S**elf-checking: 自动检查 PASS/FAIL
- **T**imely: 测试应该与代码同时开发

#### 示例：好的测试 vs 坏的测试

**❌ 坏的测试**:
```assembly
# test_bad.S
# 问题: 不 self-checking，需要人工查看寄存器值

li x10, 5
li x11, 3
add x12, x10, x11
# 没有检查 x12 是否等于 8
```

**✅ 好的测试**:
```assembly
# test_good.S
# Self-checking: 自动验证结果

li x10, 5
li x11, 3
add x12, x10, x11

# 验证结果
li x13, 8
bne x12, x13, fail

pass:
  li a0, 0  # Return 0 (success)
  j end

fail:
  li a0, 1  # Return 1 (failure)

end:
  # 退出仿真
```

---

### 5.3 Coverage-Driven 测试

#### Coverage Closure 流程

```
1. 运行 regression + 收集 coverage
   ↓
2. 分析 coverage 报告，找出未覆盖的代码
   ↓
3. 分类未覆盖代码:
   ├─ Dead code (unreachable)     → 标记为 exclude
   ├─ Debug-only code             → 标记为 exclude
   ├─ Corner case                 → 编写 directed test
   └─ Random reachable            → 增加 random tests
   ↓
4. 运行新测试，验证 coverage 提升
   ↓
5. 重复直到达到目标 coverage
```

---

## 六、Testlist 维护规范

### 6.1 Testlist 命名规范

**格式**: `testlist_<suite>-<target>-<mode>.yaml`

**示例**:
```
testlist_riscv-tests-cv64a6_imafdc_sv39-p.yaml
            │           │                  │
            │           │                  └─ mode: p (physical) / v (virtual)
            │           └─ target: cv64a6_imafdc_sv39
            └─ suite: riscv-tests
```

---

### 6.2 Testlist 内容规范

**必需字段**:
```yaml
name: "Human-readable name"
description: "Purpose of this testlist"

tests:
  - test: <test_name>           # 必需
    iterations: <num>           # 可选，默认 1
    rtl_test: <true|false>      # 必需
    iss: <spike|...>            # 必需
    timeout: <seconds>          # 可选，默认 300
```

**可选字段**:
```yaml
    seed: <num>                 # 固定随机种子
    args: "<additional_args>"   # 额外参数
    env_vars:                   # 环境变量
      KEY: value
```

---

### 6.3 添加新测试到 Testlist

#### Step-by-Step 流程

```bash
# 1. 创建测试文件
cd verif/tests/custom/my_feature/
vim my_test.S

# 2. 编译测试（验证语法）
$RISCV/bin/riscv64-unknown-elf-gcc \
  -march=rv64imafdc -mabi=lp64d \
  -static -mcmodel=medany \
  -o my_test.elf my_test.S

# 3. 本地运行测试
cd ../../sim
python3 cva6.py \
  --target cv64a6_imafdc_sv39 \
  --iss veri-testharness,spike \
  --c_tests ../tests/custom/my_feature/my_test.c

# 4. 验证通过后，添加到 testlist
vim ../tests/testlist_custom.yaml

# 添加以下内容:
  - test: my_feature/my_test
    iterations: 1
    rtl_test: true
    iss: spike
    timeout: 120

# 5. 运行完整 testlist 验证
python3 cva6.py \
  --testlist ../tests/testlist_custom.yaml \
  --target cv64a6_imafdc_sv39 \
  --iss veri-testharness,spike
```

---

## 七、测试质量指标

### 7.1 测试有效性指标

| 指标 | 定义 | 目标 | 当前 |
|------|------|------|------|
| **Bug Detection Rate** | 测试发现的 bug 数 / 总 bug 数 | >80% | ~75% |
| **False Positive Rate** | 误报测试失败 / 总失败 | <5% | ~8% |
| **Flaky Test Rate** | Flaky tests / 总测试数 | <2% | ~5% |
| **Test Execution Time** | P95 测试运行时间 | <SLA | 见 §4.2 |

---

### 7.2 Regression Health 指标

#### 每周监控指标

| 指标 | 计算方式 | 目标 |
|------|----------|------|
| **Regression Pass Rate** | PASS runs / Total runs | >95% |
| **Coverage Trend** | 当前 cov - 上周 cov | ≥0% (不下降) |
| **Mean Time To Repair (MTTR)** | 从失败到修复的平均时间 | <24 hr |
| **Test Growth Rate** | 新增测试 / 总测试数 | +2-5% / month |

---

## 八、未来改进计划

### 8.1 短期改进（Q1-Q2 2026）

| 改进项 | 目标 | 预期效果 |
|--------|------|----------|
| **增加 riscv-dv 随机测试** | 500 → 1000 tests | 发现更多 corner cases |
| **Functional coverage 扩展** | 70% → 85% | 更好的功能验证完整性 |
| **Benchmark 集成** | 添加 Embench, SPEC2006 | 性能回归检测 |

---

### 8.2 中期改进（Q3-Q4 2026）

| 改进项 | 目标 | 预期效果 |
|--------|------|----------|
| **UVM Testbench 完善** | 完整 UVM 环境 | 随机约束测试 |
| **Coverage closure** | Line >95%, Func >85% | 极致验证完整性 |
| **Multi-core tests** | 双核 lockstep 测试 | 支持多核配置验证 |

---

### 8.3 长期改进（2027+）

| 改进项 | 目标 | 预期效果 |
|--------|------|----------|
| **ML-based test generation** | AI 生成针对性测试 | 自动化 coverage closure |
| **Formal verification** | Model checking 关键路径 | 数学证明正确性 |
| **FPGA co-simulation** | 硬件加速仿真 | 运行真实 OS (Linux boot) |

---

## 九、总结

### 9.1 关键要点

**测试分层**:
- ✅ PR Smoke: 20-30 min, >60% coverage
- ✅ Nightly: 4-6 hr, >80% coverage
- ✅ Weekly: 8-12 hr, >90% coverage

**Coverage 目标**:
- Line: >90%
- Branch: >85%
- FSM: >95%
- Functional: >70%

**Regression 策略**:
- PR: 0% 失败率（阻塞 merge）
- Nightly: <5% 失败率
- Weekly: <3% 失败率

---

### 9.2 如何使用本策略

**对于测试开发者**:
1. 遵循 FIRST 原则编写测试
2. 新功能必须添加测试
3. 测试添加到合适的 testlist

**对于 CI 维护者**:
1. 监控 coverage 趋势
2. 定期 review known failures
3. 优化 regression 运行时间

**对于验证工程师**:
1. 使用 coverage 报告指导测试编写
2. 定期分析 regression 失败原因
3. 持续改进测试质量

---

**相关文档**:
- [01_ci_for_beginners.md](./01_ci_for_beginners.md) - 测试分层基础概念
- [02_current_cva6_ci_inventory.md](./02_current_cva6_ci_inventory.md) - 现有 testlist 清单
- [06_ci_triage_playbook.md](./06_ci_triage_playbook.md) - 测试失败排查
