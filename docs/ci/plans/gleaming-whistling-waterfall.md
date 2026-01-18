# CVA6 OpenHW CI/Regression 能力建设 - 执行计划 (优化版)

**版本**: v3.0（CI优先，DSim次要）
**创建日期**: 2026-01-18
**更新日期**: 2026-01-18
**计划类型**: 明天领导汇报 + 6周核心交付 + 6周优化扩展

---

## 执行摘要

**目标**: 为 CVA6 建立 OpenHW 自主可控的 **CI/Regression 能力**（不是DSim调试项目）

**核心理念**: **先建立完整的CI闭环（Verilator + Questa），DSim作为可选扩展**

**时间线**:
- **6周核心交付**: 完整CI能力（PR CI + Weekly Regression + 报告网站）
- **6周扩展优化**: DSim集成（可选）+ 性能优化 + 文档完善

**优先级重排**（基于老板的5个任务）:

| 任务 | 老板原始要求 | 优先级 | 计划周数 | 理由 |
|------|------------|--------|---------|------|
| Task 3 | GitHub Actions PR CI (Verilator) | **P0** ⭐⭐⭐⭐⭐ | Week 1-2 | CI的核心，每个PR必经 |
| Task 1 | APU testbench (Verilator + Questa) | **P0** ⭐⭐⭐⭐ | Week 2-3 | 基础测试能力 |
| Task 4 | Weekly Regression (Questa优先) | **P0** ⭐⭐⭐⭐ | Week 4-5 | 完整回归能力 |
| Task 5 | 公开报告网站 | **P0** ⭐⭐⭐⭐⭐ | Week 5-6 | CI可见性 |
| Task 1 | APU testbench (DSim) | **P1** ⭐⭐ | Week 7-8 | 锦上添花 |
| Task 2/4 | UVM testbench (DSim) | **P2** ⭐ | Week 9-12 | 如果有时间 |

**关键调整**:
- ✅ **Week 1-2**: GitHub Actions 上线（不是Week 4）
- ✅ **Week 3-4**: Questa完整集成（利用已有基础）
- ✅ **Week 5-6**: 完整CI闭环（核心交付完成）
- ✅ **Week 7-12**: DSim集成（可选）+ 优化

**团队**: 1 人（您）

**现有基础设施**（强调可用的）:
- ✅ **Verilator v5.008** 已安装并可运行 - **立即可用**
- ✅ **Spike ISS** 已安装并可运行 - **立即可用**
- ✅ **QuestaSim** 已安装 - **需验证但基础好**
- 🟡 DSim 已安装 - **存在问题，降为次要**

**核心交付物（6周后）**:
1. ✅ GitHub Actions PR CI（Verilator，<15分钟反馈）
2. ✅ QuestaSim APU + UVM 完整支持
3. ✅ Weekly regression 自动化（Verilator + Questa）
4. ✅ 公开报告网站（https://openhwgroup.github.io/cva6/）
5. ✅ 完整文档体系（9个文档 + 维护手册）

**成功标准（6周）**:
- PR CI 自动运行，每个PR必经检查
- Weekly regression 稳定运行（无人工干预）
- 测试通过率 >95%
- Code coverage >85% (Questa)
- 报告网站公开可访问

---

## 一、6周核心计划（CI能力优先）

### Phase 1 (Week 1-2): GitHub Actions PR CI 上线 ⭐⭐⭐⭐⭐

**目标**: 建立PR-level CI，快速反馈代码变更（这是CI的核心！）

---

#### Week 1: Verilator验证 + GitHub Actions设计

**Day 1: 环境基线验证**
- 验证 Verilator + Spike smoke test 通过率（30分钟）
- 验证 QuestaSim 安装和 license（30分钟）
- 记录工具版本和环境变量
- **交付**: 环境验证报告

**Day 2: GitHub Actions Workflow 设计**
- 研究现有 `.github/workflows/ci.yml`
- 设计 PR smoke test workflow（基于Verilator）
- 选择代表性测试（10-15个测试，覆盖关键功能）
- **交付**: Workflow 设计文档

**Day 3: Self-hosted Runner 配置**
- 配置 GitHub Actions runner
- 设置标签（self-hosted, linux, cva6）
- 验证 runner 可访问 Verilator 和工具链
- **交付**: Runner 配置文档

**Day 4: 创建 PR Workflow**
- 创建 `.github/workflows/pr-smoke-verilator.yml`
- 配置 cache 策略（toolchain, verilator, spike）
- 配置 checkout 和 submodule
- **交付**: Workflow 文件（初版）

**Day 5: 本地测试和文档**
- 本地测试 workflow（使用 act 或直接运行）
- 完善文档（已完成的9个文档）
- 准备 Week 2 启动
- **交付**: Week 1 总结报告

**Week 1 可验证交付物**:
- [x] 文档已完成：`docs/ci/*.md` (9个文档) ✅
- [ ] Verilator smoke test 验证通过（20+ 测试）
- [ ] Self-hosted runner 配置完成
- [ ] PR workflow 初版完成
- [ ] 环境配置文档更新

**关键命令**:
```bash
# Day 1: 验证 Verilator baseline
cd verif/sim
DV_SIMULATORS=veri-testharness,spike \
DV_TARGET=cv64a6_imafdc_sv39 \
bash ../regress/smoke-tests-cv64a6_imafdc_sv39.sh

# 记录通过率和运行时间
```

---

#### Week 2: PR CI 上线和优化

**Day 1: PR Workflow 完善**
- 添加测试结果上传（artifacts）
- 配置失败时的日志摘要
- 测试 workflow 触发（创建测试PR）
- **交付**: Workflow 运行成功

**Day 2: Cache 优化**
- 验证 toolchain cache 命中率
- 优化 Verilator 构建 cache
- 测试冷启动 vs 热启动时间
- **目标**: 冷启动 <30min，热启动 <15min
- **交付**: Cache 性能报告

**Day 3: PR 评论集成**
- 使用 `actions/github-script` 添加 PR 评论
- 显示测试结果摘要（通过/失败/运行时间）
- 失败时显示错误摘要
- **交付**: PR 评论功能

**Day 4: 多配置测试**
- 扩展矩阵：cv64a6_imafdc_sv39, cv32a65x
- 测试并行运行
- 验证结果汇总
- **交付**: 多配置支持

**Day 5: 文档和验证**
- 更新 `03_how_ci_runs_end_to_end.md`（GitHub Actions部分）
- 创建 PR CI 维护文档
- 运行完整测试验证
- **交付**: Week 2 总结 + PR CI 上线

**Week 2 可验证交付物**:
- [ ] `.github/workflows/pr-smoke-verilator.yml` 上线
- [ ] PR 自动运行测试（每个新PR触发）
- [ ] Cache 命中率 >80%
- [ ] 运行时间 <15 分钟（cache命中）
- [ ] PR 评论显示测试结果
- [ ] 文档更新完成

**PR Workflow 示例**:
```yaml
name: PR Smoke Test (Verilator)
on:
  pull_request:
    branches: [master, main]

jobs:
  verilator-smoke:
    runs-on: [self-hosted, linux, cva6]
    strategy:
      matrix:
        target: [cv64a6_imafdc_sv39]

    steps:
    - uses: actions/checkout@v4
      with:
        submodules: recursive

    - name: Cache toolchain
      uses: actions/cache@v3
      with:
        path: tools/riscv-toolchain/
        key: ${{ runner.os }}-riscv-toolchain-v1

    - name: Setup environment
      run: |
        export RISCV=$PWD/tools/riscv-toolchain
        export NUM_JOBS=8
        source verif/sim/setup-env.sh

    - name: Run Smoke Test
      run: |
        DV_SIMULATORS=veri-testharness,spike \
        DV_TARGET=${{ matrix.target }} \
        bash verif/regress/smoke-tests-${{ matrix.target }}.sh

    - name: Upload Results
      if: always()
      uses: actions/upload-artifact@v4
      with:
        name: smoke-test-results-${{ matrix.target }}
        path: verif/sim/out_*/

    - name: Comment PR
      if: always()
      uses: actions/github-script@v7
      with:
        script: |
          const fs = require('fs');
          const result = fs.readFileSync('verif/sim/smoke_test_summary.txt', 'utf8');
          github.rest.issues.createComment({
            issue_number: context.issue.number,
            owner: context.repo.owner,
            repo: context.repo.repo,
            body: `## Smoke Test Results\n\n${result}`
          });
```

**Phase 1 完成标准**:
- ✅ PR CI 自动运行
- ✅ 测试结果自动评论到 PR
- ✅ 运行时间 <15 分钟
- ✅ 通过率 >95%

---

### Phase 2 (Week 3-4): QuestaSim 完整集成 ⭐⭐⭐⭐

**目标**: 利用已安装的 QuestaSim，建立商业仿真器支持

---

#### Week 3: QuestaSim APU Testbench 集成

**Day 1: QuestaSim 环境验证**
- 验证 QuestaSim 安装和版本
- 验证 license 可用性
- 研究现有 Makefile 中的 questa targets
- **交付**: QuestaSim 环境报告

**Day 2: APU Testbench 配置**
- 在 `verif/sim/Makefile` 验证 questa-testharness target
- 配置编译选项（vlog, vopt, vsim）
- 运行第一个测试（rv64ui-p-add）
- **交付**: QuestaSim 编译通过

**Day 3: Smoke Test 验证**
- 运行 10+ smoke tests
- 调试失败案例
- 创建 `verif/regress/smoke-tests-questa-cv64a6.sh`
- **交付**: Smoke test 脚本

**Day 4: Coverage 配置**
- 配置 code coverage（vcover）
- 运行带 coverage 的测试
- 生成初步 coverage 报告
- **交付**: Coverage 配置完成

**Day 5: 性能对比和文档**
- 对比 Verilator vs Questa 性能
- 记录编译时间、仿真时间、内存消耗
- 更新文档
- **交付**: Week 3 总结

**Week 3 可验证交付物**:
- [ ] QuestaSim 成功运行 smoke test（20+ 测试）
- [ ] `verif/regress/smoke-tests-questa-cv64a6.sh` 脚本
- [ ] Coverage 报告（初版）
- [ ] 性能对比报告

---

#### Week 4: QuestaSim UVM Testbench 验证

**Day 1: UVM 环境验证**
- 验证 QuestaSim UVM 库可用
- 研究现有 `verif/tb/uvmt/` UVM testbench
- 编译 UVM testbench
- **交付**: UVM 编译通过

**Day 2: UVM Smoke Test**
- 运行 UVM firmware test
- 运行 UVM compliance test
- 调试失败案例
- **交付**: 5+ UVM 测试通过

**Day 3: UVM Regression 脚本**
- 创建 `verif/regress/uvm-smoke-questa-cv64a6.sh`
- 测试 20+ UVM 测试
- 记录通过率
- **交付**: UVM smoke test 脚本

**Day 4: UVM Coverage**
- 配置 functional coverage
- 收集 covergroup 数据
- 生成 UVM coverage 报告
- **交付**: UVM coverage 报告

**Day 5: 文档和总结**
- 更新 `02_current_cva6_ci_inventory.md`（QuestaSim部分）
- 创建 QuestaSim 维护文档
- Phase 2 总结
- **交付**: Week 4 总结

**Week 4 可验证交付物**:
- [ ] QuestaSim UVM 编译通过
- [ ] UVM smoke test 通过（20+ 测试）
- [ ] `verif/regress/uvm-smoke-questa-cv64a6.sh` 脚本
- [ ] UVM coverage 报告
- [ ] QuestaSim 完整文档

**Phase 2 完成标准**:
- ✅ QuestaSim APU testbench 完全可用
- ✅ QuestaSim UVM testbench 完全可用
- ✅ Coverage 收集正常
- ✅ 通过率 >90%

---

### Phase 3 (Week 5-6): Weekly Regression + 报告系统 ⭐⭐⭐⭐⭐

**目标**: 建立完整的 weekly regression 和公开报告网站（核心交付完成）

---

#### Week 5: Weekly Regression 框架

**Day 1: Regression 脚本设计**
- 设计 weekly regression 测试套件
  - riscv-arch-test (全集)
  - riscv-tests (全集)
  - benchmarks (coremark, dhrystone)
- 估算运行时间（目标 <12 hours）
- **交付**: Regression 设计文档

**Day 2: 创建 Weekly Regression 脚本**
- 创建 `verif/regress/weekly-regression-verilator.sh`
- 创建 `verif/regress/weekly-regression-questa.sh`
- 配置并行执行策略
- **交付**: Regression 脚本（初版）

**Day 3: Coverage 收集**
- 配置 Verilator coverage（如果支持）
- 配置 Questa coverage merge
- 运行带 coverage 的 regression
- **交付**: Coverage 数据库

**Day 4: GitHub Actions Scheduled Workflow**
- 创建 `.github/workflows/weekly-regression.yml`
- 配置 cron 触发（每周日 00:00）
- 配置 workflow_dispatch（手动触发）
- **交付**: Scheduled workflow

**Day 5: 测试和优化**
- 测试完整 weekly regression
- 优化并行度
- 记录运行时间和资源消耗
- **交付**: Week 5 总结

**Week 5 可验证交付物**:
- [ ] `verif/regress/weekly-regression-verilator.sh` 脚本
- [ ] `verif/regress/weekly-regression-questa.sh` 脚本
- [ ] `.github/workflows/weekly-regression.yml` workflow
- [ ] 完整 regression 运行成功（至少一次）
- [ ] 运行时间 <12 hours
- [ ] Coverage 数据库生成

**Weekly Regression Workflow 示例**:
```yaml
name: Weekly Regression
on:
  schedule:
    - cron: '0 0 * * 0'  # 每周日 00:00 UTC
  workflow_dispatch:  # 手动触发

jobs:
  verilator-regression:
    runs-on: [self-hosted, linux, cva6]
    steps:
    - uses: actions/checkout@v4
      with:
        submodules: recursive

    - name: Setup environment
      run: |
        export RISCV=$PWD/tools/riscv-toolchain
        export NUM_JOBS=16
        source verif/sim/setup-env.sh

    - name: Run Weekly Regression (Verilator)
      run: |
        bash verif/regress/weekly-regression-verilator.sh

    - name: Upload Coverage
      uses: actions/upload-artifact@v4
      with:
        name: verilator-coverage
        path: verif/sim/coverage/

  questa-regression:
    runs-on: [self-hosted, linux, cva6]
    steps:
    - uses: actions/checkout@v4
      with:
        submodules: recursive

    - name: Run Weekly Regression (Questa)
      run: |
        bash verif/regress/weekly-regression-questa.sh

    - name: Generate Coverage Report
      run: |
        cd verif/sim
        vcover merge merged.ucdb questa_results/*.ucdb
        vcover report -html -htmldir cov_html merged.ucdb

    - name: Upload Coverage
      uses: actions/upload-artifact@v4
      with:
        name: questa-coverage
        path: verif/sim/cov_html/
```

---

#### Week 6: 报告系统 + 公开网站

**Day 1: 报告生成脚本**
- 创建 `verif/scripts/generate_weekly_report.py`
- 解析测试日志（Verilator + Questa）
- 生成 YAML/JSON 报告
- **交付**: 报告生成脚本

**Day 2: GitHub Pages 设置**
- 创建 `gh-pages` branch
- 设计 Dashboard 布局（简单HTML）
- 配置 Jekyll 或静态站点
- **交付**: 网站框架

**Day 3: 报告上传自动化**
- 在 weekly regression workflow 中添加报告生成步骤
- 自动 commit 报告到 gh-pages
- 测试报告更新
- **交付**: 自动化流程

**Day 4: Dashboard 完善**
- 添加测试趋势图（Chart.js 或类似）
- 添加 coverage 趋势
- 添加失败测试历史
- **交付**: Dashboard v1.0

**Day 5: 项目文档和交付**
- 创建 `CORE_DELIVERY_SUMMARY.md`（6周核心交付总结）
- 更新所有文档为最终版本
- 准备汇报材料
- **交付**: Week 6 总结 + 核心交付完成

**Week 6 可验证交付物**:
- [ ] `verif/scripts/generate_weekly_report.py` 脚本
- [ ] 公开网站上线（https://openhwgroup.github.io/cva6/）
- [ ] 第一份 weekly report 发布
- [ ] Dashboard 显示测试结果和 coverage
- [ ] 完整项目文档
- [ ] 核心交付总结文档

**报告格式示例**:
```markdown
# CVA6 Weekly Regression Report - Week 6

## Summary
- **Date**: 2026-01-25
- **Tests Run**: 450 (Verilator: 250, Questa: 200)
- **Tests Passed**: 445 (98.9%)
- **Tests Failed**: 5 (1.1%)
- **Code Coverage**: 87.3% (Questa)

## Test Breakdown

### Verilator (veri-testharness + Spike)
- riscv-arch-test: 120/120 ✅
- riscv-tests: 110/110 ✅
- benchmarks: 20/20 ✅

### QuestaSim (APU + UVM)
- APU testbench: 100/100 ✅
- UVM firmware: 45/50 ⚠️ (5 failures)
- UVM compliance: 50/50 ✅

## Failed Tests
1. `rv64mi-p-csr` (Questa UVM) - Timeout
2. `custom_test_1` (Questa UVM) - Assertion failure
3-5. [其他失败详情]

## Coverage Highlights (QuestaSim)
- Frontend: 92.1%
- Execute Stage: 89.5%
- LSU: 81.2% ⚠️ (below 85% target)
- Cache: 88.7%

## Actions
- [ ] Investigate LSU coverage gap
- [ ] Fix rv64mi-p-csr timeout issue
- [ ] Add directed tests for uncovered paths

## Trends
- Test pass rate: 98.9% (↑ 0.5% from last week)
- Coverage: 87.3% (↑ 1.2% from last week)
```

**Phase 3 完成标准**:
- ✅ Weekly regression 自动运行（每周日）
- ✅ 报告自动生成和发布
- ✅ 公开网站可访问
- ✅ Dashboard 显示最新结果
- ✅ 测试通过率 >95%
- ✅ Coverage >85%

---

## 二、6周扩展计划（DSim + 优化）

### Phase 4 (Week 7-8): 优化 + DSim APU（可选）⭐⭐

**目标**: 性能优化、文档完善、DSim APU testbench（如果有时间）

---

#### Week 7: 性能优化和文档完善

**Day 1-2: CI 性能优化**
- 并行化测试（GNU Parallel）
- 优化 cache 策略
- 减少 regression 运行时间（目标 -20%）
- **交付**: 性能优化报告

**Day 3-4: 文档完善**
- 完善所有 9 个文档
- 创建 CI 维护手册
- 创建故障排查指南
- **交付**: 完整文档体系 v2.0

**Day 5: 用户培训材料**
- 创建快速上手指南（5分钟）
- 创建视频教程（可选）
- 准备团队培训材料
- **交付**: 培训材料

**Week 7 可验证交付物**:
- [ ] Regression 运行时间减少 20%
- [ ] 所有文档更新到 v2.0
- [ ] CI 维护手册
- [ ] 用户培训材料

---

#### Week 8: DSim APU Testbench（可选）

**注意**: 本周为**可选任务**，仅在前7周顺利完成的情况下进行。

**Day 1: DSim 环境诊断**
- 运行 DSim testharness，记录错误
- 分类错误：语法错误 vs 运行时错误
- 评估修复工作量
- **交付**: DSim 问题清单

**Day 2-3: DSim 语法问题修复**
- 修复高优先级语法错误
- 修复 const 数组声明问题
- 修复 interface/modport 警告
- **交付**: 部分测试通过

**Day 4: DSim Smoke Test**
- 运行 DSim smoke test
- 目标：至少 10 个测试通过
- 创建 `verif/regress/smoke-tests-dsim-cv64a6.sh`
- **交付**: DSim smoke test 脚本

**Day 5: 文档和总结**
- 记录 DSim 修复过程
- 更新文档
- Week 8 总结
- **交付**: DSim 集成报告

**Week 8 可验证交付物**:
- [ ] DSim smoke test 通过率 >50% (如果有时间)
- [ ] DSim 问题修复记录
- [ ] DSim 配置文档

**如果 Week 8 DSim 进展不顺利**:
- 停止 DSim 工作
- 转而优化现有 CI（Verilator + Questa）
- 准备项目总结

---

### Phase 5 (Week 9-12): DSim UVM（可选）或持续优化

**目标**: DSim UVM 移植（如果有时间）或持续优化现有 CI

---

#### 选项 A: DSim UVM 移植（如果 Week 8 顺利）

**Week 9-10: DSim UVM 编译和测试**
- 参考原计划 Week 7-10 的 DSim UVM 部分
- 目标：DSim UVM 编译通过，运行基本测试
- 预计难度高，风险大

**Week 11-12: DSim 完整集成**
- DSim weekly regression
- DSim coverage
- 文档和交付

---

#### 选项 B: 持续优化（推荐）

**Week 9-10: CI 增强**
- Smart test selection（PR 仅运行相关测试）
- 增量 coverage
- 测试并行度优化
- **交付**: CI 性能提升 30%

**Week 11: Dashboard 增强**
- 历史趋势分析
- 失败测试自动 bisect
- 实时状态监控
- **交付**: Dashboard v2.0

**Week 12: 项目交付和知识转移**
- 创建 `PROJECT_FINAL_SUMMARY.md`
- 团队培训和知识转移
- 准备最终汇报
- **交付**: 项目完整交付

**Week 9-12 可验证交付物（选项 B）**:
- [ ] CI 性能提升 30%
- [ ] Dashboard v2.0 上线
- [ ] 知识转移完成
- [ ] 最终项目报告

---

## 三、明天汇报要点（核心优化版）

### 3.1 汇报结构建议

**时长**: 20-30 分钟（含 Q&A）

**核心信息**: **6周完成核心CI能力，DSim是可选扩展**

**结构**:
1. **项目背景和目标** (3 分钟)
2. **优先级调整：CI优先，DSim次要** (3 分钟) ⭐⭐⭐
3. **6周核心计划** (10 分钟) ⭐⭐⭐⭐⭐
4. **扩展计划（Week 7-12）** (3 分钟)
5. **风险和资源需求** (3 分钟)
6. **Q&A** (5 分钟)

---

### 3.2 核心汇报内容

#### 幻灯片 1: 项目背景

**问题陈述**:
- 当前 CVA6 依赖 Thales 内部 GitLab CI
- OpenHW 需要自主可控的 CI/Regression 能力
- 需要支持开源仿真器（Verilator）+ 商业仿真器（QuestaSim）

**项目目标**:
- 建立 PR-level CI（快速反馈）
- 建立 weekly regression（全面测试）
- 公开发布测试结果（透明度）
- 支持多种仿真器（Verilator + QuestaSim 优先，DSim 可选）

---

#### 幻灯片 2: 优先级调整（关键信息）⭐⭐⭐

**调整理由**:
1. **这是CI项目，不是DSim调试项目**
2. **Verilator 和 QuestaSim 已经可用，应优先利用**
3. **DSim 存在兼容性问题，风险高，收益不确定**

**优先级重排**:

| 任务 | 原计划 | 调整后 | 理由 |
|------|--------|--------|------|
| GitHub Actions PR CI | Week 4 | **Week 1-2** ⭐⭐⭐⭐⭐ | CI的核心 |
| QuestaSim 集成 | Week 5 | **Week 3-4** ⭐⭐⭐⭐ | 已安装，可用 |
| Weekly Regression + 报告 | Week 6,12 | **Week 5-6** ⭐⭐⭐⭐⭐ | 核心交付 |
| DSim APU | Week 1-3 | **Week 7-8** ⭐⭐ (可选) | 降为次要 |
| DSim UVM | Week 7-10 | **Week 9-12** ⭐ (可选) | 如果有时间 |

**关键信息**:
- ✅ **6周完成核心CI能力**（Verilator + QuestaSim）
- ✅ **DSim作为可选扩展**（不影响核心交付）
- ✅ **风险大幅降低**（利用已有基础）

---

#### 幻灯片 3-5: 6周核心计划（每2周一个里程碑）⭐⭐⭐⭐⭐

**Month 1 (Week 1-2): GitHub Actions PR CI**
- Week 1: Verilator验证、Workflow设计、Runner配置
- Week 2: PR CI上线、Cache优化、评论集成

**里程碑 M1** (Week 2 完成):
- ✅ PR CI 自动运行
- ✅ <15 分钟反馈
- ✅ 测试结果自动评论
- ✅ 通过率 >95%

**Month 2 (Week 3-4): QuestaSim 完整集成**
- Week 3: QuestaSim APU testbench + Coverage
- Week 4: QuestaSim UVM testbench + Smoke test

**里程碑 M2** (Week 4 完成):
- ✅ QuestaSim APU 完全可用
- ✅ QuestaSim UVM 完全可用
- ✅ Coverage >85%
- ✅ 通过率 >90%

**Month 3 (Week 5-6): Weekly Regression + 报告网站**
- Week 5: Weekly regression 框架、Scheduled workflow
- Week 6: 报告生成、GitHub Pages、Dashboard

**里程碑 M3** (Week 6 完成) - **核心交付完成**:
- ✅ Weekly regression 自动运行
- ✅ 报告网站公开上线
- ✅ Dashboard 显示结果
- ✅ 测试通过率 >95%
- ✅ Coverage >85%

**6周核心交付物**:
1. ✅ GitHub Actions PR CI（Verilator）
2. ✅ QuestaSim APU + UVM 完整支持
3. ✅ Weekly regression 自动化（Verilator + Questa）
4. ✅ 公开报告网站
5. ✅ 完整文档体系（9个文档 + 维护手册）

---

#### 幻灯片 6: 扩展计划（Week 7-12）

**Week 7-8: 优化 + DSim APU（可选）**
- Week 7: 性能优化、文档完善、培训材料
- Week 8: DSim APU testbench（如果有时间）

**Week 9-12: 两个选项**
- **选项 A**: DSim UVM 移植（如果 Week 8 顺利）
- **选项 B**: 持续优化（推荐）- Smart test selection、Dashboard v2.0

**关键信息**:
- DSim 作为**锦上添花**，不是核心目标
- 如果 DSim 进展不顺利，立即转向优化现有 CI
- **核心交付不受 DSim 影响**

---

#### 幻灯片 7: 风险和缓解

| 风险 | 概率 | 影响 | 缓解策略 |
|------|------|------|---------|
| **Verilator 版本不兼容** | 低 | 中 | 已验证可用，有 patch |
| **QuestaSim license 限制** | 中 | 低 | 错峰运行，申请更多 license |
| **Self-hosted runner 不稳定** | 中 | 低 | 配置监控，准备备用 |
| **DSim 问题复杂度超预期** | 高 | **低** | 降为可选，不影响核心交付 ✅ |

**关键风险缓解**:
- ✅ **DSim 降为次要优先级**，核心交付不依赖 DSim
- ✅ **利用已验证的工具**（Verilator + Questa）
- ✅ **分阶段交付**，每2周一个里程碑

---

#### 幻灯片 8: 资源需求

**人力**:
- 您（全职）: 6 周核心 + 6 周扩展
- IT 支持（兼职）: ~3 天（runner配置、license）

**硬件**（Self-hosted runner）:
- CPU: 32-64 cores
- Memory: 128-256 GB
- Disk: 1-2 TB SSD
- 估算成本: $8,000-$12,000（一次性）或 $400/月（云端）

**软件 License**（假设已有）:
- ✅ Verilator（开源，免费）
- ✅ QuestaSim license
- ❓ DSim license（Week 7+ 可选）

---

#### 幻灯片 9: 预期交付

**6周核心交付** ⭐⭐⭐⭐⭐:
- ✅ GitHub Actions PR CI（<15 分钟反馈）
- ✅ QuestaSim APU + UVM 完整支持
- ✅ Weekly regression 自动化（~500 tests, <12 hours）
- ✅ 公开报告网站（https://openhwgroup.github.io/cva6/）
- ✅ 完整文档体系

**12周扩展交付**（可选）:
- ⭐⭐ DSim APU testbench（如果顺利）
- ⭐ DSim UVM testbench（如果有时间）
- ⭐⭐⭐⭐ CI 性能优化、Dashboard v2.0（推荐）

**成功标准（6周）**:
- PR CI 自动运行，每个 PR 必经检查
- Weekly regression 稳定运行（无人工干预）
- 测试通过率 >95%
- Code coverage >85% (QuestaSim)
- 报告网站公开可访问

---

#### 幻灯片 10: Next Steps

**本周行动**（如果批准）:
- **Day 1**: 验证 Verilator + Spike baseline
- **Day 2**: 设计 GitHub Actions workflow
- **Day 3**: 配置 self-hosted runner
- **Day 4**: 创建 PR workflow 初版
- **Day 5**: 本地测试和文档

**需要的支持**:
- ✅ 确认 QuestaSim license 可用
- ✅ 确认 self-hosted runner 硬件（或云端）
- ✅ GitHub repo admin 权限（添加 runner）
- ❓ 确认 DSim 是否为必需（建议：可选）

---

### 3.3 汇报技巧

**强调优势**:
- ✅ "我们重新评估了优先级，**将CI能力放在首位**"
- ✅ "Verilator 和 QuestaSim 已经可用，**可以立即开始**"
- ✅ "**6周完成核心CI能力**，包括PR CI、Weekly Regression、报告网站"
- ✅ "DSim 作为**可选扩展**，不影响核心交付"

**诚实面对挑战**:
- "DSim 存在兼容性问题，修复时间不确定"
- "我建议**先建立完整的CI闭环**，再考虑扩展到 DSim"
- "这样可以**降低风险，提前交付价值**"

**展示规划能力**:
- "我已经设计了详细的6周核心计划，每2周一个里程碑"
- "每周都有明确的交付物，可以快速验证进展"
- "如果 DSim 是必需的，我们可以在 Week 7-12 重点攻坚，但建议作为可选"

---

## 四、关键文件和路径清单

### 4.1 核心交付文件（6周）

**GitHub Actions**:
- `.github/workflows/pr-smoke-verilator.yml` - PR CI ⭐⭐⭐⭐⭐
- `.github/workflows/weekly-regression.yml` - Weekly regression ⭐⭐⭐⭐⭐

**Regression 脚本**:
- `verif/regress/smoke-tests-questa-cv64a6.sh` - QuestaSim smoke test
- `verif/regress/uvm-smoke-questa-cv64a6.sh` - QuestaSim UVM smoke
- `verif/regress/weekly-regression-verilator.sh` - Verilator weekly
- `verif/regress/weekly-regression-questa.sh` - QuestaSim weekly

**报告系统**:
- `verif/scripts/generate_weekly_report.py` - 报告生成
- `gh-pages/index.html` - Dashboard 主页
- `gh-pages/reports/*.json` - 周报数据

**文档**（已完成）:
- `docs/ci/*.md` - 9个核心文档 ✅
- `docs/ci/CI_MAINTENANCE_GUIDE.md` - 维护手册（新建）

### 4.2 扩展文件（Week 7-12，可选）

**DSim（如果进行）**:
- `verif/regress/smoke-tests-dsim-cv64a6.sh` - DSim smoke test
- `verif/regress/uvm-smoke-dsim-cv64a6.sh` - DSim UVM smoke

**优化（推荐）**:
- `verif/scripts/smart_test_selection.py` - Smart test selection
- `verif/scripts/incremental_coverage.py` - 增量 coverage
- `gh-pages/v2/` - Dashboard v2.0

---

## 五、成功因素总结

### 5.1 技术可行性 ✅

**强**:
- ✅ Verilator 和 Spike 已验证可用
- ✅ QuestaSim 已安装，基础好
- ✅ 现有 Makefile 和脚本可复用
- ✅ GitHub Actions 已有配置可参考

**弱**:
- 🟡 DSim 存在兼容性问题（已降为次要）

**评估**: **95% 可行**（核心部分），DSim 为 **60% 可行**（可选部分）

---

### 5.2 时间合理性 ✅

**6周核心时间线**:
- Week 1-2: PR CI - **轻松**（基于 Verilator）
- Week 3-4: QuestaSim - **中等**（已安装）
- Week 5-6: Regression + 报告 - **中等**（脚本复用）

**6周扩展时间线**:
- Week 7: 优化和文档 - **轻松**
- Week 8-12: DSim 或持续优化 - **看情况**

**评估**: **非常合理且保守**

---

### 5.3 依赖风险 ✅

**外部依赖**:
- Verilator: **已有** ✅
- QuestaSim license: **已有** ✅
- Self-hosted runner 硬件: **需确认**
- DSim license: **可选**

**评估**: **依赖风险低**

---

## 六、推进建议

### Week 1 Day 1 立即行动（如果批准）

**上午**:
1. 验证 Verilator + Spike baseline（1 小时）
   ```bash
   cd verif/sim
   DV_SIMULATORS=veri-testharness,spike \
   DV_TARGET=cv64a6_imafdc_sv39 \
   bash ../regress/smoke-tests-cv64a6_imafdc_sv39.sh
   ```
2. 记录通过率和运行时间

**下午**:
1. 验证 QuestaSim 安装和 license（30 分钟）
2. 研究现有 `.github/workflows/ci.yml`（1 小时）
3. 设计 PR workflow 初版（1 小时）

**晚上**:
1. 准备 Week 1 Day 2 工作
2. 创建 `pr-smoke-verilator.yml` 草稿

---

## 七、总结：核心信息

**给领导的核心信息**:

1. **我们重新评估了优先级**：CI能力优先，DSim次要
2. **6周完成核心CI能力**：PR CI + QuestaSim + Weekly Regression + 报告网站
3. **DSim作为可选扩展**：Week 7-12，不影响核心交付
4. **风险大幅降低**：利用已验证的 Verilator 和 QuestaSim
5. **每2周一个里程碑**：快速验证进展，及时调整

**如果领导问"为什么调整优先级？"**:
- "这是CI项目，核心目标是建立回归测试能力，而不是调试特定仿真器"
- "Verilator 和 QuestaSim 已经可用，我们应该优先利用它们快速建立CI闭环"
- "DSim 存在兼容性问题，修复时间不确定，建议作为可选扩展"
- "这样可以在6周内交付完整的CI能力，然后再考虑扩展到 DSim"

**如果领导坚持 DSim 是必需的**:
- "理解，那我建议：**前6周仍然优先完成核心CI（Verilator + Questa）**"
- "**Week 7-12 重点攻坚 DSim**，这样即使 DSim 遇到问题，核心CI也已上线"
- "这种分阶段策略可以**降低风险，确保至少有可用的CI系统**"

---

**计划状态**: READY FOR REVIEW v3.0 - CI优先版本
