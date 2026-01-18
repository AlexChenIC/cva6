# CVA6 OpenHW Regression 能力建设 - 执行计划

**版本**: v2.0（基于实际环境状态更新）
**创建日期**: 2026-01-18
**计划类型**: 明天领导汇报 + 12周执行路线图

---

## 执行摘要

**目标**: 为 CVA6 建立 OpenHW 自主可控的 CI/Regression 能力

**时间线**: 12 周（现实版，核心功能优先）

**优先级**:
1. APU testbench 三仿真器支持（Verilator ✅ + DSim 🟡 + Questa ✅）
2. GitHub Actions PR CI（基于 Verilator）
3. UVM testbench DSim/Questa 移植（重点攻坚）
4. Weekly regression 自动化
5. 公开报告网站

**团队**: 1 人（您）

**现有基础设施** ✅:
- ✅ Verilator v5.008 已安装并可运行
- ✅ Spike ISS 已安装并可运行
- ✅ QuestaSim 已安装
- 🟡 DSim 已安装，testharness 可运行基本测试（rv64ui-p-add）
- ❌ DSim UVM 存在编译错误（SV语法、UVM宏、包导入混合问题）

**关键发现**（基于代码探索）:
- CVA6 已有完整的 DSim 支持框架（`verif/core-v-verif/mk/uvmt/dsim.mk`）
- 存在 DSIM 特定的代码路径（`ifdef DSIM`）
- 可复用资源丰富（Makefile、脚本、testbench 结构）
- 主要挑战：DSim 对 SV 语法的严格性导致 UVM 编译失败

---

## 一、文档体系规划（9 个模块）

### 1.1 仓库文档（CVA6 repo: `docs/ci/` 或 `verif/docs/ci/`）

**技术文档**（面向开发者和 CI 维护者）:

1. **`00_overview.md`**
   - CI 系统总体架构图
   - 当前状态 vs 目标状态对比
   - 关键文件清单和索引

2. **`01_ci_for_beginners.md`**
   - CI 基础概念（smoke test、regression、coverage）
   - PR-level vs nightly/weekly 区别
   - 最小 CI 闭环示例
   - 常见 CI 失败类型和排查路径

3. **`02_current_cva6_ci_inventory.md`**
   - 当前 GitLab CI 清单（.gitlab-ci.yml 解析）
   - 当前 GitHub Actions 清单
   - 现有测试矩阵
   - 现有工具链和依赖

4. **`03_how_ci_runs_end_to_end.md`**
   - CI 触发流程（push → build → test → report）
   - 每个 job 的详细说明
   - Artifacts 流转
   - Dashboard 更新机制

5. **`05_ci_contract.md`**
   - CI 保证什么（PASS 代表什么）
   - CI 不保证什么（限制和边界）
   - SLA 定义（运行时间、成功率）
   - 失败处理策略

6. **`06_ci_triage_playbook.md`**
   - CI 失败分类决策树
   - 每种失败的排查步骤
   - 常见问题和解决方案
   - Escalation 流程

7. **`07_test_and_regression_strategy.md`**
   - 测试分层策略（smoke/nightly/weekly）
   - 测试选择原则
   - Coverage 目标
   - Testlist 维护规范

8. **`08_runner_and_license_checklist.md`**
   - Self-hosted runner 环境要求
   - License 配置检查清单
   - 工具版本锁定策略
   - 故障排查命令

9. **`09_glossary.md`**
   - CI 术语表（中英文对照）
   - CVA6 特定术语
   - 工具和命令速查

### 1.2 Wiki 文档（OpenHW 内部 Wiki）

**入门和协作文档**（面向新人和管理层）:

1. **快速开始指南**
   - 5 分钟跑通第一个 CI
   - 常用命令速查卡
   - 问题求助渠道

2. **每周 CI 状态报告模板**
   - Tests run / passed / failed
   - Coverage 趋势
   - 新增/修复的问题
   - 下周计划

3. **CI 变更申请模板**
   - 添加新测试的流程
   - 修改 CI 配置的 review 流程

---

---

## 一、可复用资源分析（已有基础）

### 1.1 仿真器支持现状

| 仿真器 | Testharness | UVM | 状态 | 可复用性 |
|--------|------------|-----|------|---------|
| **Verilator** | ✅ 完全支持 | ❌ 不支持UVM | 生产可用 | ⭐⭐⭐⭐⭐ 100% |
| **Spike** | ✅ ISS参考 | ✅ Tandem | 生产可用 | ⭐⭐⭐⭐⭐ 100% |
| **VCS** | ✅ 完全支持 | ✅ 完全支持 | GitLab CI使用 | ⭐⭐⭐⭐ 80% 可参考 |
| **QuestaSim** | ✅ 已安装 | 🟡 需验证 | 需配置 | ⭐⭐⭐⭐ 90% 可复用 |
| **DSim** | 🟡 基本可用 | ❌ 编译失败 | 需修复 | ⭐⭐⭐ 60% 需调试 |
| **Xcelium** | ✅ 部分支持 | 🟡 部分支持 | 未验证 | ⭐⭐ 30% 参考 |

### 1.2 关键可复用文件

**Makefile 和脚本** (⭐⭐⭐⭐⭐ 高度可复用):
- `verif/sim/Makefile` - 通用仿真器编译/运行框架
- `verif/sim/cva6.py` - 参数化测试执行引擎
- `verif/sim/setup-env.sh` - 环境变量设置
- `verif/regress/*.sh` - 28个回归测试脚本模板
- `verif/core-v-verif/mk/uvmt/dsim.mk` - **DSim 专用 Makefile**

**Testbench 基础设施** (⭐⭐⭐⭐ 需少量修改):
- `corev_apu/tb/ariane_testharness.sv` - APU testbench 顶层
- `corev_apu/tb/ariane_tb.sv` - TB 主模块
- `verif/tb/uvmt/uvmt_cva6_tb.sv` - UVM TB 顶层
- `verif/env/uvme/` - UVM 环境（需修复 DSim 兼容性）

**CI 配置** (⭐⭐⭐⭐ 可直接扩展):
- `.github/workflows/ci.yml` - GitHub Actions 矩阵配置
- `.gitlab-ci.yml` - GitLab CI 参考（6阶段流程）

**已知的 DSim 特定代码** (⭐⭐⭐ 需理解和扩展):
```systemverilog
// verif/core-v-verif/cv32e40p/env/corev-dv/target/cv32e40p/riscv_core_setting.sv
`ifdef DSIM
  privileged_reg_t implemented_csr[] = { ... };  // 动态数组
`else
  const privileged_reg_t implemented_csr[] = { ... };  // 常量数组
`endif
```

### 1.3 DSim 已有支持分析

**位置**: `verif/core-v-verif/mk/uvmt/dsim.mk`

**关键配置**:
```makefile
# 编译选项
DSIM_CMP_FLAGS = $(TIMESCALE) $(SV_CMP_FLAGS) -top uvmt_$(CV_CORE_LC)_tb

# 错误抑制（已知问题）
DSIM_ERR_SUPPRESS = MultiBlockWrite:ReadingOutputModport

# Coverage 配置
DSIM_COMPILE_ARGS += -code-cov block -code-cov-scope-specs $(DSIM_CODE_COV_SCOPE)

# DPI 库链接
-sv_lib $(UVM_HOME)/src/dpi/libuvm_dpi.so
-sv_lib $(DPI_DASM_LIB)
-sv_lib $(abspath $(SVLIB_LIB))
```

**可复用**:
- ✅ 编译 flags 模板
- ✅ Coverage 配置方案
- ✅ DPI 链接方法
- ✅ 错误抑制规则
- 🟡 需要修复 UVM 部分的兼容性

---

## 二、12周执行计划（核心功能优先）

### 阶段划分

**Phase 1 (Week 1-3)**: 基础巩固 - Verilator + DSim Testharness
**Phase 2 (Week 4-6)**: GitHub Actions + QuestaSim APU
**Phase 3 (Week 7-10)**: DSim/Questa UVM 移植（核心攻坚）
**Phase 4 (Week 11-12)**: Weekly Regression + 报告系统

---

### Week 1: 环境验证 + DSim Testharness 调试

**目标**: 验证现有工具，修复 DSim testharness 的已知问题

#### 本周任务模块

**模块 1.1: 环境基线验证** (Day 1) ✅
- 验证 Verilator + Spike smoke test 通过率
- 验证 QuestaSim 安装和 license
- 记录工具版本和环境变量

**模块 1.2: DSim Testharness 问题诊断** (Day 2-3) 🔴 关键
- 运行 DSim smoke test，记录所有失败案例
- 分类错误：语法错误 vs 运行时错误
- 创建问题清单和优先级排序

**模块 1.3: DSim 语法问题修复** (Day 4-5)
- 修复 interface/modport 警告（MultiBlockWrite）
- 修复 const 数组声明问题
- 验证修复后至少 10 个测试通过

#### 可验证交付物
- [x] 文档已完成：`docs/ci/*.md` (9个文档)
- [ ] DSim smoke test 通过率 >80% (至少 8/10 测试)
- [ ] DSim 问题清单和修复记录
- [ ] 环境配置文档更新（DSim 特定配置）

#### 本周依赖
- ✅ Verilator v5.008 (已安装)
- ✅ Spike (已安装)
- ✅ QuestaSim (已安装)
- ✅ DSim (已安装，需调试)

#### 关键命令
```bash
# 验证 Verilator baseline
cd verif/sim
DV_SIMULATORS=veri-testharness,spike \
DV_TARGET=cv64a6_imafdc_sv39 \
bash ../regress/smoke-tests-cv64a6_imafdc_sv39.sh

# 运行 DSim smoke test（当前可部分通过）
cd verif/sim
make -C ../core-v-verif/mk SIMULATOR=dsim comp
# 记录每个测试的结果
```

#### 风险与规避
| 风险 | 概率 | 影响 | 规避策略 |
|------|------|------|---------|
| DSim 语法错误数量超预期 | 高 | 中 | 分批修复，先解决高频错误 |
| Interface 兼容性问题复杂 | 中 | 高 | 参考 core-v-verif 的 DSim 配置 |

---

### Week 2: DSim Testharness 完成 + Verilator 优化

**目标**: 达到 DSim testharness 生产可用，优化 Verilator 性能

#### 本周任务模块

**模块 2.1: DSim Testharness 完成** (Day 1-2)
- 修复剩余语法问题
- 达到 smoke test 100% 通过（至少 20 个测试）
- 创建 `verif/regress/smoke-tests-dsim-cv64a6.sh`

**模块 2.2: Verilator 性能优化** (Day 3)
- 测试 Verilator v5.030（最新版本）
- 优化编译选项（-O3, --threads）
- Benchmark 编译和仿真时间

**模块 2.3: QuestaSim APU Testharness 验证** (Day 4-5)
- 验证 QuestaSim testharness 可运行
- 创建 `verif/regress/smoke-tests-questa-cv64a6.sh`
- 对比三种仿真器性能

#### 可验证交付物
- [ ] DSim smoke test 100% 通过（20+ 测试）
- [ ] `verif/regress/smoke-tests-dsim-cv64a6.sh` 脚本
- [ ] `verif/regress/smoke-tests-questa-cv64a6.sh` 脚本
- [ ] 三仿真器性能对比报告（Markdown）

#### 关键指标
```
Verilator: 编译 ~5 min, 仿真 ~2 min/test
DSim:      编译 ~2 min, 仿真 ~1 min/test (目标)
QuestaSim: 编译 ~3 min, 仿真 ~1.5 min/test (目标)
```

---

### Week 3: DSim 代码覆盖率 + 文档完善

**目标**: 启用 DSim coverage，完成 Phase 1 交付

#### 本周任务模块

**模块 3.1: DSim Coverage 配置** (Day 1-2)
- 启用 `-code-cov block` 选项
- 配置 `ccov_scopes.txt` 覆盖范围
- 运行带 coverage 的回归测试

**模块 3.2: Coverage 报告生成** (Day 3)
- 合并多个测试的 coverage 数据库
- 生成 HTML 报告
- 分析覆盖率指标（目标 >60%）

**模块 3.3: Phase 1 文档和总结** (Day 4-5)
- 更新所有文档为最终版本
- 创建 `PHASE1_DELIVERY_SUMMARY.md`
- 准备中期汇报材料

#### 可验证交付物
- [ ] DSim coverage HTML 报告
- [ ] Coverage >60% (line coverage)
- [ ] Phase 1 完成总结文档
- [ ] 中期汇报 PPT/Markdown

#### Phase 1 完成标准
- ✅ 3种仿真器 testharness 全部可用
- ✅ Smoke test 脚本完成
- ✅ 基础 coverage 收集可用
- ✅ 文档体系完整

---

### Week 4: GitHub Actions PR Workflow

**目标**: 创建 PR-level CI，快速反馈代码变更

#### 本周任务模块

**模块 4.1: GitHub Actions Workflow 设计** (Day 1-2)
- 创建 `.github/workflows/pr-apu-smoke.yml`
- 配置测试矩阵（Verilator + 多配置）
- 设置 cache 策略（toolchain, verilator, spike）

**模块 4.2: PR 评论集成** (Day 3)
- 实现测试结果自动评论
- 失败时显示详细日志摘要
- 成功时显示运行时间和通过率

**模块 4.3: 优化和测试** (Day 4-5)
- 优化运行时间目标 <15 分钟
- 测试 cache 命中率 >80%
- 验证多个 PR 并行运行

#### 可验证交付物
- [ ] Self-hosted runner 成功运行 Verilator smoke test
- [ ] GitHub Actions workflow: `.github/workflows/pr-smoke-verilator.yml`
- [ ] Cache 命中率 >80%（toolchain, verilator, spike）
- [ ] 文档：`03_how_ci_runs_end_to_end.md` (Verilator 部分)
- [ ] 运行时间 <15 分钟（smoke test）

#### 本周依赖
- **Runner**: Self-hosted Linux runner（需配置）
- **权限**: GitHub repo settings（添加 runner）
- **工具**: 与 Week 1 相同

#### 执行步骤
```bash
# Day 1: 配置 self-hosted runner
# 在 runner 机器上安装 GitHub Actions runner
# https://docs.github.com/en/actions/hosting-your-own-runners

# Day 2-3: 创建 workflow
# 参考现有 .github/workflows/ci.yml
# 简化为仅 smoke test（5-10 个代表性测试）

# Day 4: 测试 cache
# 验证 cache 策略（toolchain, verilator, spike）
# 第一次运行 ~30 分钟
# 第二次运行（cache 命中）~10 分钟

# Day 5: 文档
# 记录 workflow 配置和故障排查步骤
```

#### Workflow 示例
```yaml
name: PR Smoke Test (Verilator)
on: [pull_request]

jobs:
  verilator-smoke:
    runs-on: [self-hosted, linux, cva6]
    steps:
    - uses: actions/checkout@v4
      with:
        submodules: recursive

    - name: Cache toolchain
      uses: actions/cache@v3
      with:
        path: tools/riscv-toolchain/
        key: ${{ runner.os }}-toolchain-${{ hashFiles('ci/install-toolchain.sh') }}

    - name: Run Smoke Test
      run: |
        export RISCV=$PWD/tools/riscv-toolchain
        source verif/sim/setup-env.sh
        DV_SIMULATORS=veri-testharness,spike \
        DV_TARGET=cv64a6_imafdc_sv39 \
        bash verif/regress/smoke-tests-cv64a6_imafdc_sv39.sh

    - name: Upload Results
      uses: actions/upload-artifact@v4
      with:
        name: verilator-smoke-results
        path: verif/sim/out*
```

#### 风险点与规避
- **风险**: Self-hosted runner 磁盘空间不足
  - **规避**: 定期清理 tmp/ 和 tools/（保留 cache）
- **风险**: Cache 失效导致重复构建
  - **规避**: 固定 hash keys，避免频繁变更安装脚本

#### 需要对齐的问题
- Self-hosted runner 的标签命名约定（如 `[self-hosted, linux, cva6]`）
- 是否需要在 PR 评论中显示测试结果？

---

### Week 5: QuestaSim APU Testbench 集成

**目标**: 完成 QuestaSim APU testbench 的完整集成

#### 本周任务模块

**模块 5.1: QuestaSim Makefile Targets** (Day 1-2)
- 在 `verif/sim/Makefile` 添加 questa-testharness
- 配置编译选项（vlog, vopt, vsim）
- 测试 10+ smoke tests

**模块 5.2: QuestaSim Coverage 配置** (Day 3-4)
- 配置 code coverage（vcover）
- 测试 coverage merge
- 生成 HTML 报告

**模块 5.3: 性能对比和文档** (Day 5)
- 对比 Verilator/DSim/Questa 性能
- 更新文档：QuestaSim 配置指南
- 创建故障排查 FAQ

#### 可验证交付物
- [ ] `make questa-testharness` 可用
- [ ] QuestaSim coverage 报告
- [ ] 三仿真器对比报告（完整版）

---

### Week 6: Self-hosted Runner + Weekly Regression 框架

**目标**: 搭建 self-hosted runner，设计 weekly regression

#### 本周任务模块

**模块 6.1: Self-hosted Runner 配置** (Day 1-2)
- 安装 GitHub Actions runner
- 配置标签（self-hosted, linux, cva6）
- 验证 DSim/Questa license 可用

**模块 6.2: Weekly Regression 脚本** (Day 3-4)
- 创建 `verif/regress/weekly-regression.sh`
- 整合所有测试套件（~1000 tests）
- 配置并行执行（利用多核）

**模块 6.3: GitHub Actions Scheduled Workflow** (Day 5)
- 创建 `.github/workflows/weekly-regression.yml`
- 配置 cron 触发（每周日 00:00）
- 测试手动触发（workflow_dispatch）

#### 可验证交付物
- [ ] Self-hosted runner 运行成功
- [ ] Weekly regression 脚本完成
- [ ] Scheduled workflow 测试通过

---

### Week 7-8: DSim UVM Testbench 移植（第一阶段）

**目标**: 解决 DSim UVM 编译错误，实现基本 UVM 测试

#### Week 7 任务模块

**模块 7.1: UVM 编译错误分析** (Day 1-2) 🔴 关键
- 运行 DSim UVM 编译，收集所有错误
- 分类错误：
  - SystemVerilog 语法错误
  - UVM 宏定义问题
  - Package 导入问题
  - DPI-C 链接问题
- 创建优先级修复清单

**模块 7.2: SystemVerilog 语法修复** (Day 3-5)
- 修复 `const` 数组声明（添加 `ifdef DSIM`）
- 修复 interface 使用问题
- 修复时序敏感的语句
- 目标：减少编译错误 >50%

#### Week 8 任务模块

**模块 8.1: UVM 宏和包问题修复** (Day 1-3)
- 修复 UVM_* 宏定义
- 解决 package 导入顺序问题
- 验证 UVM 库路径配置

**模块 8.2: DPI-C 集成** (Day 4-5)
- 修复 DPI function 声明
- 链接 libuvm_dpi.so
- 链接 Spike DPI 库
- 验证基本 DPI 调用可用

#### 可验证交付物
- [ ] DSim UVM 编译通过（无 error）
- [ ] 至少 1 个 UVM 测试运行成功
- [ ] UVM 问题修复清单和记录

---

### Week 9-10: DSim/Questa UVM Testbench 完成（第二阶段）

**目标**: 完成 UVM testbench 移植，运行完整测试套件

#### Week 9 任务模块

**模块 9.1: DSim UVM Smoke Test** (Day 1-3)
- 运行 UVM firmware test
- 运行 UVM compliance test
- 调试失败案例
- 目标：5+ UVM 测试通过

**模块 9.2: QuestaSim UVM 验证** (Day 4-5)
- 验证 QuestaSim UVM 编译
- 运行 UVM smoke test
- 对比 DSim/Questa 结果一致性

#### Week 10 任务模块

**模块 10.1: UVM Regression 脚本** (Day 1-3)
- 创建 `verif/regress/uvm-regression-dsim.sh`
- 创建 `verif/regress/uvm-regression-questa.sh`
- 测试 ~200 UVM 测试
- 目标：通过率 >90%

**模块 10.2: UVM Coverage 配置** (Day 4-5)
- 配置 functional coverage
- 收集 covergroup 数据
- 生成 UVM coverage 报告

#### 可验证交付物
- [ ] DSim UVM regression 通过率 >90%
- [ ] Questa UVM regression 通过率 >90%
- [ ] UVM coverage 报告
- [ ] UVM 测试文档

---

### Week 11: Weekly Regression 完整集成

**目标**: 整合所有测试，实现完整 weekly regression

#### 本周任务模块

**模块 11.1: 完整 Regression Workflow** (Day 1-3)
- 整合 APU testharness tests (Verilator/DSim/Questa)
- 整合 UVM tests (DSim/Questa)
- 配置并行执行策略
- 预计运行时间：8-10 hours

**模块 11.2: Coverage 收集和合并** (Day 4-5)
- 合并所有仿真器的 coverage 数据
- 生成统一的 coverage 报告
- 分析 coverage holes
- 目标：Line coverage >85%

#### 可验证交付物
- [ ] Weekly regression 完整运行成功
- [ ] 运行时间 <12 hours
- [ ] 统一 coverage 报告
- [ ] 测试通过率 >95%

---

### Week 12: 报告系统 + 项目交付

**目标**: 完成报告系统，项目收尾

#### 本周任务模块

**模块 12.1: GitHub Pages 设置** (Day 1-2)
- 创建 gh-pages branch
- 配置 Jekyll 或静态 HTML
- 设计 Dashboard 布局

**模块 12.2: 报告生成自动化** (Day 3-4)
- 创建 `generate_weekly_report.py`
- 解析测试结果和 coverage
- 生成 HTML/Markdown 报告
- 自动上传到 GitHub Pages

**模块 12.3: 项目文档和交付** (Day 5)
- 创建 `PROJECT_DELIVERY_SUMMARY.md`
- 更新所有文档为最终版本
- 准备最终汇报材料
- 知识转移文档

#### 可验证交付物
- [ ] 公开网站上线（https://openhwgroup.github.io/cva6/）
- [ ] 第一份 weekly report 发布
- [ ] 完整项目文档
- [ ] 最终汇报 PPT

#### 项目完成标准（12周交付）
- ✅ Task 1: APU testbench 三仿真器支持
- ✅ Task 2: UVM testbench DSim/Questa 支持（核心功能）
- ✅ Task 3: GitHub Actions PR CI
- ✅ Task 4: Weekly regression 自动化
- ✅ Task 5: 公开报告网站

---

## 三、任务模块总览

### 3.1 核心任务模块统计

| 模块编号 | 模块名称 | 工作日 | 难度 | 优先级 | 依赖 |
|---------|---------|--------|------|--------|------|
| 1.1 | 环境基线验证 | 1 | ⭐ | P0 | - |
| 1.2 | DSim Testharness 诊断 | 2 | ⭐⭐⭐ | P0 | 1.1 |
| 1.3 | DSim 语法问题修复 | 2 | ⭐⭐⭐⭐ | P0 | 1.2 |
| 2.1 | DSim Testharness 完成 | 2 | ⭐⭐⭐ | P0 | 1.3 |
| 2.2 | Verilator 性能优化 | 1 | ⭐⭐ | P1 | - |
| 2.3 | QuestaSim APU 验证 | 2 | ⭐⭐ | P0 | - |
| 3.1 | DSim Coverage 配置 | 2 | ⭐⭐⭐ | P1 | 2.1 |
| 3.2 | Coverage 报告生成 | 1 | ⭐⭐ | P1 | 3.1 |
| 3.3 | Phase 1 文档和总结 | 2 | ⭐ | P0 | 3.2 |
| 4.1 | GitHub Actions Workflow | 2 | ⭐⭐ | P0 | - |
| 4.2 | PR 评论集成 | 1 | ⭐⭐ | P1 | 4.1 |
| 4.3 | 优化和测试 | 2 | ⭐⭐ | P1 | 4.2 |
| 5.1 | QuestaSim Makefile | 2 | ⭐⭐ | P0 | - |
| 5.2 | QuestaSim Coverage | 2 | ⭐⭐⭐ | P1 | 5.1 |
| 5.3 | 性能对比和文档 | 1 | ⭐ | P0 | 5.2 |
| 6.1 | Self-hosted Runner 配置 | 2 | ⭐⭐ | P0 | - |
| 6.2 | Weekly Regression 脚本 | 2 | ⭐⭐⭐ | P0 | - |
| 6.3 | Scheduled Workflow | 1 | ⭐⭐ | P0 | 6.1, 6.2 |
| 7.1 | UVM 编译错误分析 | 2 | ⭐⭐⭐⭐ | P0 | - |
| 7.2 | SV 语法修复 | 3 | ⭐⭐⭐⭐⭐ | P0 | 7.1 |
| 8.1 | UVM 宏和包修复 | 3 | ⭐⭐⭐⭐⭐ | P0 | 7.2 |
| 8.2 | DPI-C 集成 | 2 | ⭐⭐⭐⭐ | P0 | 8.1 |
| 9.1 | DSim UVM Smoke Test | 3 | ⭐⭐⭐⭐ | P0 | 8.2 |
| 9.2 | QuestaSim UVM 验证 | 2 | ⭐⭐⭐ | P0 | 9.1 |
| 10.1 | UVM Regression 脚本 | 3 | ⭐⭐⭐ | P0 | 9.2 |
| 10.2 | UVM Coverage 配置 | 2 | ⭐⭐⭐⭐ | P1 | 10.1 |
| 11.1 | 完整 Regression Workflow | 3 | ⭐⭐⭐ | P0 | 10.2 |
| 11.2 | Coverage 收集和合并 | 2 | ⭐⭐⭐ | P1 | 11.1 |
| 12.1 | GitHub Pages 设置 | 2 | ⭐⭐ | P1 | - |
| 12.2 | 报告生成自动化 | 2 | ⭐⭐⭐ | P0 | 12.1 |
| 12.3 | 项目文档和交付 | 1 | ⭐ | P0 | 12.2 |

**总计**: 30个核心模块，60个工作日（12周）

### 3.2 难度和风险分布

**难度 ⭐⭐⭐⭐⭐ (最高难度)**: 3个模块
- 7.2: SV 语法修复 (DSim UVM)
- 8.1: UVM 宏和包修复

**难度 ⭐⭐⭐⭐**: 5个模块
- 1.3: DSim 语法问题修复
- 7.1: UVM 编译错误分析
- 8.2: DPI-C 集成
- 9.1: DSim UVM Smoke Test
- 10.2: UVM Coverage 配置

**关键路径** (Critical Path):
```
1.1 → 1.2 → 1.3 → 2.1 → ... → 7.1 → 7.2 → 8.1 → 8.2 → 9.1 → 10.1 → 11.1 → 12.2
```

**最大风险**: Week 7-10 (UVM 移植)，需要预留 buffer 时间

---

## 四、明天汇报要点（重点）

### 4.1 汇报结构建议

**时长**: 20-30 分钟（含 Q&A）

**结构**:
1. **项目背景和目标** (3 分钟)
2. **现状评估和可复用资源** (5 分钟) ⭐
3. **12周执行计划** (8 分钟) ⭐⭐
4. **风险和缓解策略** (4 分钟) ⭐
5. **资源需求和预期交付** (5 分钟)
6. **Q&A** (5 分钟)

---

### 4.2 核心汇报内容

#### 幻灯片 1: 项目背景

**问题陈述**:
- 当前 CVA6 依赖 Thales 内部 GitLab CI
- OpenHW 需要自主可控的 CI/Regression 能力
- 需要支持 Verilator (开源) + DSim/QuestaSim (商业)

**项目目标**:
- 建立 3仿真器 APU testbench 支持
- 移植 UVM testbench 到 DSim/QuestaSim
- 创建 GitHub Actions PR CI
- 实现 weekly regression 自动化
- 公开发布测试结果

---

#### 幻灯片 2-3: 现状评估（强调已有基础）⭐

**现有基础设施** ✅:
| 组件 | 状态 | 可复用性 |
|------|------|---------|
| Verilator | ✅ 完全可用 | ⭐⭐⭐⭐⭐ 100% |
| Spike ISS | ✅ 完全可用 | ⭐⭐⭐⭐⭐ 100% |
| QuestaSim | ✅ 已安装 | ⭐⭐⭐⭐ 90% |
| DSim testharness | 🟡 基本可用 | ⭐⭐⭐ 60% |
| DSim UVM | ❌ 编译失败 | ⭐⭐ 30% |

**关键发现**:
- CVA6 已有完整的 DSim 支持框架 (`verif/core-v-verif/mk/uvmt/dsim.mk`)
- 28个现成的回归测试脚本可复用
- GitHub Actions 和 GitLab CI 配置可参考
- 主要挑战：DSim 对 SV 语法的严格性

**这意味着**: 不是从零开始，是在成熟基础上扩展！

---

#### 幻灯片 4-6: 12周执行计划（每月一个里程碑）⭐⭐

**Month 1 (Week 1-4): 基础巩固**
- Week 1: DSim testharness 调试和修复
- Week 2: 三仿真器 smoke test 全部可用
- Week 3: Coverage 收集和 Phase 1 交付
- Week 4: GitHub Actions PR workflow 上线

**里程碑 M1**:
- ✅ APU testbench 三仿真器支持
- ✅ PR CI 自动运行

**Month 2 (Week 5-8): UVM 攻坚**
- Week 5: QuestaSim APU 完整集成
- Week 6: Weekly regression 框架搭建
- Week 7-8: DSim UVM 编译错误修复（核心难点）

**里程碑 M2**:
- ✅ QuestaSim 完整支持
- ✅ DSim UVM 编译通过

**Month 3 (Week 9-12): UVM 完成和交付**
- Week 9-10: UVM regression 测试和调优
- Week 11: Weekly regression 完整集成
- Week 12: 报告系统和项目交付

**里程碑 M3**:
- ✅ 所有 5个任务完成
- ✅ 公开网站上线

---

#### 幻灯片 7: 风险和缓解⭐

| 风险 | 概率 | 影响 | 缓解策略 |
|------|------|------|---------|
| **DSim UVM语法错误超预期** | 高 | 阻塞 | ① 分批修复<br>② 联系 Metrics 技术支持<br>③ 预留 2周 buffer |
| **License 并发限制** | 中 | 中 | ① 错峰运行<br>② 申请更多 license |
| **Self-hosted runner 不稳定** | 中 | 低 | ① 配置监控<br>② 准备备用 runner |
| **Coverage 数据过大** | 低 | 低 | ① 定期清理<br>② 仅保留 4周数据 |

**关键风险缓解**:
- Week 7-8 是关键期（UVM），已预留充足时间
- 随时准备 escalate 到 Metrics/Siemens 技术支持

---

#### 幻灯片 8: 资源需求

**人力**:
- 您（全职）: 12 周
- IT 支持（兼职）: ~5 天（runner配置、license）

**硬件**（如需 self-hosted runner）:
- CPU: 32-64 cores
- Memory: 128-256 GB
- Disk: 1-2 TB SSD
- 估算成本: $8,000-$12,000（一次性）或 $400/月（云端）

**软件 License**（假设已有）:
- ✅ DSim license
- ✅ QuestaSim license
- ❓ 是否需要增加并发数？

---

#### 幻灯片 9: 预期交付

**12周后交付物**:
- ✅ APU testbench 三仿真器支持（Verilator/DSim/QuestaSim）
- ✅ UVM testbench DSim/QuestaSim 支持（核心功能）
- ✅ GitHub Actions PR CI（<15 分钟反馈）
- ✅ Weekly regression 自动化（~1000 tests, <12 hours）
- ✅ 公开报告网站（https://openhwgroup.github.io/cva6/）
- ✅ 完整文档体系（9个技术文档 + 汇报材料）

**成功标准**:
- APU smoke test 通过率 >95%
- UVM regression 通过率 >90%
- Code coverage >85%
- Weekly regression 稳定运行（无人工干预）

---

#### 幻灯片 10: Next Steps

**本周行动**（如果批准）:
- Day 1: 开始 DSim testharness 诊断
- Day 2-3: 修复高优先级语法错误
- Day 4-5: 验证修复效果，准备 Week 2

**需要的支持**:
- ✅ 确认 DSim/QuestaSim license 可用
- ✅ 确认 self-hosted runner 硬件（如需要）
- ✅ GitHub repo admin 权限（添加 runner）

---

### 4.3 汇报技巧

**强调亮点**:
- ✅ "我们已经有60%的基础，不是从零开始"
- ✅ "DSim testharness 已经可以运行基本测试"
- ✅ "已有完整的 DSim Makefile 框架可以参考"
- ✅ "计划详细且可验证，每周都有明确交付物"

**诚实面对挑战**:
- "Week 7-8 的 UVM 移植是最大挑战，但我已经分析了问题类型"
- "已经识别了 DSim 特定的代码路径（`ifdef DSIM`），有先例可循"

**展示准备充分**:
- "我已经完成了代码探索，了解了所有可复用资源"
- "创建了详细的12周计划，每个模块都有工作日估算"
- "准备了风险缓解策略，不会让项目阻塞"

---

## 五、关键文件和路径清单

### 5.1 需要修改的核心文件（预计）

**Makefile 和脚本**:
- `verif/sim/Makefile` - 添加 DSim/Questa targets
- `verif/regress/smoke-tests-dsim-cv64a6.sh` - 新建
- `verif/regress/smoke-tests-questa-cv64a6.sh` - 新建
- `verif/regress/uvm-regression-dsim.sh` - 新建
- `verif/regress/uvm-regression-questa.sh` - 新建
- `verif/regress/weekly-regression.sh` - 新建

**GitHub Actions**:
- `.github/workflows/pr-apu-smoke.yml` - 新建
- `.github/workflows/weekly-uvm-regression.yml` - 新建

**UVM Testbench（需修复 DSim 兼容性）**:
- `verif/tb/uvmt/uvmt_cva6_tb.sv` - 可能需要 `ifdef DSIM`
- `verif/tb/uvmt/cva6_tb_wrapper.sv` - 可能需要修改
- `verif/env/uvme/*.sv` - UVM 环境组件

**报告系统**:
- `verif/scripts/generate_weekly_report.py` - 新建
- `docs/ci/*.md` - 更新（9个文档）
- `gh-pages/` - 新建分支和网站

### 5.2 参考文件（已存在，可复用）

**DSim 框架**:
- `verif/core-v-verif/mk/uvmt/dsim.mk` - DSim Makefile 模板
- `verif/core-v-verif/cv32e40p/env/corev-dv/target/cv32e40p/riscv_core_setting.sv` - DSim `ifdef` 示例

**VCS 框架**（可参考用于 DSim/Questa）:
- `verif/sim/Makefile` 行 271-290 - VCS UVM targets
- `.gitlab-ci/scripts/report_*.py` - 报告生成脚本

---

## 六、成功因素总结

### 6.1 技术可行性 ✅

**强**:
- CVA6 已有成熟的 CI/regression 基础设施
- DSim framework 已存在，testharness 基本可用
- 有 VCS 作为参考，可移植编译选项
- UVM 问题类型已明确（语法、宏、DPI）

**弱**:
- DSim UVM 从未成功编译过
- 语法错误数量可能超预期

**评估**: **80% 可行**，关键是 Week 7-10 的 UVM 移植

---

### 6.2 时间合理性 ✅

**12周时间线**:
- Phase 1-2 (Week 1-6): APU testbench - **相对轻松**
- Phase 3 (Week 7-10): UVM移植 - **关键挑战**，已预留4周
- Phase 4 (Week 11-12): 集成和交付 - **收尾工作**

**Buffer**: Week 8-10 有 overlap，可用于应对意外

**评估**: **合理且留有余地**

---

### 6.3 依赖风险 🟡

**外部依赖**:
- DSim/QuestaSim license: **已有** ✅
- Self-hosted runner 硬件: **需确认**
- EDA vendor 技术支持: **可选，作为后备**

**评估**: **依赖风险可控**

---

## 七、推进建议

### 立即行动（如果批准）

**Week 1 Day 1** (明天下午，如果汇报通过):
1. 验证 Verilator + Spike baseline（30 分钟）
2. 运行 DSim testharness smoke test，记录所有错误（2 小时）
3. 创建问题清单和优先级排序（1 小时）

**Week 1 Day 2-3**:
1. 修复最高频的语法错误（如 const 数组）
2. 重新测试，目标 8/10 测试通过

**Week 1 Day 4-5**:
1. 完成剩余修复
2. 创建 DSim 问题修复文档
3. 准备 Week 2 启动

---

**计划状态**: READY FOR REVIEW - 待明天汇报批准后执行
3. 创建 DSim smoke test 脚本

#### 可验证交付物
- [ ] DSim 成功运行 smoke test（至少 10 个测试 PASS）
- [ ] 脚本：`verif/regress/smoke-tests-dsim-cv64a6.sh`
- [ ] 运行时间对比报告（Verilator vs DSim）
- [ ] 文档：DSim 集成指南（添加到 `03_how_ci_runs_end_to_end.md`）

#### 本周依赖
- **工具**: DSim license（已有 ✅）
- **Runner**: Self-hosted runner（需安装 DSim）
- **参考**: 现有 GitLab CI 的 DSim 配置（如果有）

#### 执行步骤
```bash
# Day 1: DSim 环境配置
# 安装 DSim 或验证现有安装
# 配置 license 服务器

# Day 2-3: 修改 verif/sim/Makefile
# 添加 DSim targets（参考 VCS/Questa 配置）
# 或修改 verif/sim/cva6.yaml 添加 DSim ISS 配置

# Day 4: 运行测试
cd verif/sim
make dsim-testharness target=cv64a6_imafdc_sv39 elf=<testfile>

# Day 5: 创建 regression 脚本
# 参考 smoke-tests-cv64a6_imafdc_sv39.sh
# 替换 DV_SIMULATORS=dsim-testharness
```

#### 需要研究的问题
1. **CVA6 是否已有 DSim 配置？**
   - 检查 `verif/sim/Makefile` 中是否有 `dsim` targets
   - 检查 `.gitlab-ci.yml` 中是否使用过 DSim

2. **DSim vs VCS 的差异**
   - DSim 的命令行参数格式
   - Log 文件解析差异

#### 风险点与规避
- **风险**: DSim 版本不兼容
  - **规避**: 联系 Metrics 支持，使用推荐版本
- **风险**: License 并发限制
  - **规避**: 配置 license 排队机制

#### 需要对齐的问题
- DSim 的推荐版本号？
- License 服务器地址和端口？
- 是否需要 DSim 的特殊编译选项？

---

### Week 4: QuestaSim 集成 + 测试矩阵扩展

#### 本周目标
1. 在 self-hosted runner 上配置 QuestaSim 环境
2. 验证 APU testbench 在 QuestaSim 上运行
3. 建立测试矩阵（3 种仿真器 × 多种配置）

#### 可验证交付物
- [ ] QuestaSim 成功运行 smoke test
- [ ] 测试矩阵文档：Verilator/DSim/Questa × cv64a6/cv32a65x
- [ ] 脚本：`verif/regress/smoke-tests-questa-cv64a6.sh`
- [ ] 性能对比报告（3 种仿真器的运行时间和资源消耗）

#### 本周依赖
- **工具**: QuestaSim license（已有 ✅）
- **Runner**: Self-hosted runner

#### 执行步骤
```bash
# Day 1: QuestaSim 环境配置
# 验证 QuestaSim 安装和 license

# Day 2-3: 修改 verif/sim/Makefile
# 测试 questa-testharness target

# Day 4: 运行测试
cd verif/sim
make questa-testharness target=cv64a6_imafdc_sv39 elf=<testfile>

# Day 5: 对比测试
# 同时运行 Verilator/DSim/Questa
# 记录运行时间、内存消耗、编译时间
```

#### 风险点与规避
- **风险**: QuestaSim 和 DSim 的 log 格式差异
  - **规避**: 统一 log 解析脚本（Python）

#### 需要对齐的问题
- QuestaSim 的推荐版本？
- 是否需要 UVM 支持（questa-uvm target）？

---

### Week 5: Weekly Regression 框架 + Coverage 收集

#### 本周目标
1. 建立 weekly regression 测试流程
2. 配置 code coverage 收集（DSim/Questa）
3. 生成第一份 coverage 报告

#### 可验证交付物
- [ ] Weekly regression script: `verif/regress/weekly-regression.sh`
- [ ] 支持的测试套件：
  - riscv-arch-test (全集)
  - riscv-tests (全集)
  - benchmarks (coremark, dhrystone)
- [ ] Coverage database 生成（DSim 和 Questa）
- [ ] Coverage HTML 报告
- [ ] 文档：`07_test_and_regression_strategy.md`

#### 本周依赖
- **工具**: DSim/Questa + coverage license
- **时间**: ~6-8 小时运行时间（weekly regression）

#### 执行步骤
```bash
# Day 1-2: 创建 weekly regression 脚本
#!/bin/bash
# weekly-regression.sh

export cov=1  # 启用 coverage

# 运行全部 arch-test
bash verif/regress/dv-riscv-arch-test.sh

# 运行全部 riscv-tests
bash verif/regress/dv-riscv-tests.sh

# 运行 benchmarks
bash verif/regress/benchmark.sh

# Day 3-4: Coverage 收集和报告
# DSim: 使用 DSim 的 coverage 工具
# Questa: 使用 vcover merge + vcover report

# Day 5: 生成 HTML 报告
# 合并多个测试的 coverage database
# 生成 HTML dashboard
```

#### Coverage 工具命令
```bash
# DSim coverage (待确认具体命令)
dsim -coverage ...

# QuestaSim coverage
vcover merge merged.ucdb test1.ucdb test2.ucdb test3.ucdb
vcover report -html -htmldir cov_html merged.ucdb
```

#### 风险点与规避
- **风险**: Coverage 数据库过大（>10GB）
  - **规避**: 定期清理，仅保留最近 4 周的数据

#### 需要对齐的问题
- Coverage 目标：Code coverage >90%？
- 是否需要 functional coverage（需要 UVM）？

---

### Week 6: 报告系统 + Dashboard 集成

#### 本周目标
1. 建立自动化报告生成系统
2. 集成到 GitHub PR（显示测试结果）
3. 生成第一份 weekly regression 报告

#### 可验证交付物
- [ ] 报告生成脚本：`generate_report.py`
- [ ] GitHub PR 集成：自动评论测试结果
- [ ] Weekly report 模板（Markdown）
- [ ] Dashboard（简单网页或 GitHub Pages）
- [ ] 文档：`06_ci_triage_playbook.md`

#### 本周依赖
- **参考**: `.gitlab-ci/scripts/report_*.py`

#### 执行步骤
```bash
# Day 1-2: 创建报告生成脚本
# 参考 .gitlab-ci/scripts/report_builder.py
# 解析测试日志，生成 YAML/JSON 报告

# Day 3: GitHub PR 集成
# 使用 GitHub Actions 的 actions/github-script
# 在 PR 中添加评论：
#   - ✅ 20/20 tests passed
#   - ⚠️ Coverage: 92.5%
#   - 📊 View full report

# Day 4-5: 创建 Dashboard
# 使用 GitHub Pages 或简单的 HTML
# 显示：
#   - 测试趋势图
#   - Coverage 趋势
#   - 失败测试历史
```

#### 报告格式示例
```markdown
# CVA6 Weekly Regression Report - Week 6

## Summary
- **Tests Run**: 550
- **Tests Passed**: 545 (99.1%)
- **Tests Failed**: 5 (0.9%)
- **Code Coverage**: 92.3% (+0.5% from last week)

## Failed Tests
1. rv64mi-p-csr (DSim) - Timeout
2. rv32ua-p-amoadd_w (Questa) - Assertion failure

## Coverage Highlights
- Frontend: 95.2%
- Execute Stage: 93.8%
- LSU: 89.1% ⚠️ (below target)

## Actions
- [ ] Investigate LSU coverage gap
- [ ] Fix rv64mi-p-csr timeout issue
```

#### 风险点与规避
- **风险**: 报告生成脚本复杂
  - **规避**: 先做简单版本（纯文本），后续优化

---

### Week 7-8: 优化和文档完善（可选）

#### 本周目标
1. 性能优化（减少 regression 运行时间）
2. 完善所有文档
3. 团队培训和知识转移

#### 可验证交付物
- [ ] 所有 9 个文档完成
- [ ] Wiki 页面创建
- [ ] CI 维护手册
- [ ] 团队培训材料（PPT/视频）

#### 优化方向
1. **并行化测试**
   - 使用 GNU Parallel 或 pytest-xdist
   - 减少 50% 运行时间

2. **增量 coverage**
   - 仅收集变更文件的 coverage
   - 减少 coverage merge 时间

3. **Smart test selection**
   - PR 自动检测变更文件
   - 仅运行相关测试（如仅 frontend 变更则跳过 LSU 测试）

#### 文档完善清单
- [ ] `00_overview.md` - 添加架构图
- [ ] `01_ci_for_beginners.md` - 添加 FAQ
- [ ] `05_ci_contract.md` - 明确 SLA
- [ ] `08_runner_and_license_checklist.md` - 故障排查指南
- [ ] `09_glossary.md` - 术语表

---

## 三、关键风险和规避策略

### 3.1 技术风险

| 风险 | 影响 | 概率 | 规避策略 |
|------|------|------|---------|
| Verilator 版本不兼容 | 高 | 中 | 使用 verif/regress/verilator-v5.patch |
| DSim/Questa 配置问题 | 中 | 中 | 提前与 EDA 供应商沟通 |
| Coverage 数据库过大 | 低 | 高 | 定期清理，使用增量 coverage |
| Self-hosted runner 故障 | 高 | 低 | 配置 fallback 到 GitHub-hosted runner |

### 3.2 时间风险

| 风险 | 影响 | 规避策略 |
|------|------|---------|
| 6 周时间线过紧 | 中 | 优先 Week 1-4，Week 5-6 可延后 |
| License 并发限制 | 低 | 错峰运行测试（nightly vs weekly）|
| 文档编写时间不足 | 中 | 使用模板，边做边写 |

### 3.3 资源风险

| 风险 | 影响 | 规避策略 |
|------|------|---------|
| 一个人工作量大 | 高 | 分阶段交付，优先核心功能 |
| Self-hosted runner 资源不足 | 中 | 监控 CPU/内存/磁盘使用 |

---

## 四、每周检查清单

### Week 1 检查点
- [ ] Verilator smoke test 通过
- [ ] 文档框架创建
- [ ] 环境配置脚本可复现

### Week 2 检查点
- [ ] GitHub Actions workflow 运行成功
- [ ] Cache 策略验证
- [ ] PR smoke test <15 分钟

### Week 3 检查点
- [ ] DSim 集成完成
- [ ] Smoke test 通过
- [ ] 运行时间对比

### Week 4 检查点
- [ ] QuestaSim 集成完成
- [ ] 测试矩阵建立
- [ ] 性能对比报告

### Week 5 检查点
- [ ] Weekly regression 框架
- [ ] Coverage 报告生成
- [ ] 策略文档完成

### Week 6 检查点
- [ ] 报告系统上线
- [ ] GitHub PR 集成
- [ ] Dashboard 发布

---

## 五、后续演进路线（Week 9+）

### 短期（2-4 周）
1. **UVM Testbench 集成**
   - 移植 UVM testbench 到 DSim/Questa
   - 添加 functional coverage
   - 随机测试生成（riscv-dv）

2. **Coverage Closure**
   - 识别未覆盖的 corner cases
   - 编写 directed tests
   - 达到 >95% code coverage

### 中期（2-3 月）
1. **Nightly Regression**
   - 建立 nightly regression（比 weekly 更全面）
   - 添加 stress tests 和 fuzzing

2. **Dashboard 增强**
   - 实时状态监控
   - 历史趋势分析
   - 自动 bisect 失败 commit

### 长期（6 月+）
1. **Dual-Core Lockstep 支持**
   - 扩展 testbench 支持双核配置
   - 添加 lockstep 检查器

2. **Silicon Validation**
   - FPGA 原型验证
   - ASIC tapeout 前 regression

---

## 六、成功标准

### 技术指标
- ✅ APU testbench 在 3 种仿真器上运行（Verilator/DSim/Questa）
- ✅ PR-level smoke test <15 分钟
- ✅ Weekly regression 自动化（无需人工干预）
- ✅ Code coverage >90%
- ✅ 报告自动生成和发布

### 流程指标
- ✅ 9 个文档完成
- ✅ Wiki 页面创建
- ✅ CI 维护手册可用
- ✅ 新人可在 1 天内上手

### 业务指标
- ✅ PR 合并前必经 CI 检查
- ✅ 每周 regression 报告发布
- ✅ Bug 发现率提升（通过 CI 发现的 bug 数量）

---

## 七、关键文件清单

### 现有文件（需分析）
- `.gitlab-ci.yml` - GitLab CI 配置
- `.github/workflows/ci.yml` - GitHub Actions 配置
- `verif/sim/Makefile` - 仿真 Makefile
- `verif/sim/cva6.py` - Python 测试框架
- `verif/regress/*.sh` - 回归测试脚本
- `.gitlab-ci/scripts/report_*.py` - 报告生成脚本

### 需创建的文件
- `.github/workflows/pr-smoke-verilator.yml` - PR smoke test
- `verif/regress/smoke-tests-dsim-cv64a6.sh` - DSim smoke test
- `verif/regress/smoke-tests-questa-cv64a6.sh` - Questa smoke test
- `verif/regress/weekly-regression.sh` - Weekly regression
- `scripts/generate_report.py` - 报告生成
- `docs/ci/*.md` - 9 个文档

---

## 八、需要与团队对齐的问题

### 技术决策
1. 文档存放路径：`docs/ci/` 还是 `verif/docs/ci/`？
2. Self-hosted runner 标签命名？
3. Coverage 目标：90% 还是 95%？
4. 是否需要 UVM testbench（Week 1-6 范围外）？

### 资源确认
1. Self-hosted runner 规格（CPU 核数、内存、磁盘）？
2. DSim/Questa 版本号和 license 服务器地址？
3. 是否有专门的存储服务器保存 coverage database？

### 流程确认
1. PR merge 策略：必须 CI PASS 才能合并？
2. Weekly regression 的运行时间窗口（周末？夜间？）
3. 失败的 regression 由谁负责 triage？

---

## 九、附录：命令速查

### 环境配置
```bash
export RISCV=/path/to/riscv-toolchain
export NUM_JOBS=8
source verif/sim/setup-env.sh
```

### 运行 Smoke Test
```bash
# Verilator
DV_SIMULATORS=veri-testharness,spike \
DV_TARGET=cv64a6_imafdc_sv39 \
bash verif/regress/smoke-tests-cv64a6_imafdc_sv39.sh

# DSim (待创建)
DV_SIMULATORS=dsim-testharness \
DV_TARGET=cv64a6_imafdc_sv39 \
bash verif/regress/smoke-tests-dsim-cv64a6.sh

# Questa
DV_SIMULATORS=questa-testharness \
DV_TARGET=cv64a6_imafdc_sv39 \
bash verif/regress/smoke-tests-questa-cv64a6.sh
```

### Coverage 收集
```bash
# 启用 coverage
export cov=1

# 运行测试
bash verif/regress/dv-riscv-arch-test.sh

# 生成报告（Questa）
cd verif/sim
vcover report -html -htmldir cov_html questa_results/coverage.ucdb
```

### 清理环境
```bash
make -C verif/sim clean_all
rm -rf verif/sim/out*
rm -rf verif/sim/*_results/
```

---

## 执行建议

1. **Week 1-2 是关键**：必须打好基础，确保 Verilator 和文档框架稳定
2. **每周五发送进度报告**：使用 weekly report 模板
3. **遇到阻塞立即上报**：不要独自卡壳超过 1 天
4. **文档边做边写**：不要等到最后再写文档
5. **多利用现有资源**：GitLab CI 的脚本可以复用
6. **设置每日站会**：即使一个人也要每天记录进展

---

**计划状态**: DRAFT - 待用户确认后开始执行
