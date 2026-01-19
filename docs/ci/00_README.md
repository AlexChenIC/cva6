# CVA6 CI/Regression 文档中心

**欢迎来到 CVA6 持续集成和回归测试文档中心！**

本目录包含 CVA6 CI/Regression 系统的完整文档，从入门到高级，从理论到实践。

**📁 文件夹结构**: 参见 [README_STRUCTURE.md](./README_STRUCTURE.md) 或 [FILE_TREE.txt](./FILE_TREE.txt)

---

## 📚 文档导航

### 🚀 快速开始

**如果您是第一次接触 CVA6 CI**，请按以下顺序阅读：

1. **[CI 入门指南](./01_ci_for_beginners.md)** ⭐ **从这里开始**
   - CI 是什么？为什么需要 CI？
   - Smoke test、Nightly、Weekly 的区别
   - 5 分钟快速上手示例
   - 常见问题排查

2. **[当前 CI 系统清单](./02_current_cva6_ci_inventory.md)**
   - CVA6 现有 CI 配置完整清单
   - GitLab CI vs GitHub Actions 对比
   - 所有测试脚本和 testlist
   - 工具链和依赖详解

3. **[环境配置脚本](./setup-local-env.sh)**
   - 一键配置本地开发环境
   - 自动检测和验证工具链
   - 可选：运行快速验证测试
   - 使用方法：
     ```bash
     cd docs/ci
     bash setup-local-env.sh
     ```

4. **[Week 1 执行指南](./guides/WEEK1_EXECUTION_GUIDE.md)** 🎯 **实战必读**
   - 完整的 Step-by-Step 环境配置流程
   - Smoke test 运行详细步骤
   - 常见错误和解决方案（含 SPIKE_SRC_DIR 问题）
   - 测试结果验证和报告生成
   - Week 1 完成 Checklist
   - 快速参考卡（复制粘贴即用）

### 📋 项目规划和执行

**[CVA6 CI能力建设执行计划 v3.0](./plans/gleaming-whistling-waterfall.md)** ⭐⭐⭐ **明天汇报重点**
- **核心理念**: 6周完成核心CI能力，DSim作为可选扩展
- **优先级**: GitHub Actions PR CI (Week 1-2) → QuestaSim (Week 3-4) → Weekly Regression + 报告网站 (Week 5-6)
- **明天汇报要点**: 第三部分包含10张幻灯片完整结构
- **关键调整**: CI优先，利用已验证的Verilator和QuestaSim

**相关文档**:
- [任务分析报告](./reports/TASK_ANALYSIS_REGRESSION_CAPABILITY.md) - 深度技术分析（700+行）
- [文档审查报告](./reports/DOCUMENTATION_REVIEW_REPORT.md) - 质量审查
- [Week 1 交付总结](./guides/WEEK1_DELIVERY_SUMMARY.md) - 第一周成果

### 📖 深入理解

5. **[CI 端到端流程](./03_how_ci_runs_end_to_end.md)** ✅ **已完成**
   - CI 触发机制详解
   - 每个 CI job 的执行流程
   - Artifacts 传递和报告生成
   - Dashboard 更新机制

6. **[CI 契约](./05_ci_contract.md)** ✅ **已完成**
   - CI 保证什么（PASS 的含义）
   - CI 不保证什么（边界和限制）
   - SLA 定义（运行时间、成功率）
   - 失败处理策略

7. **[CI 故障排查手册](./06_ci_triage_playbook.md)** ✅ **已完成**
   - CI 失败分类决策树
   - 每种失败的详细排查步骤
   - 常见问题和解决方案
   - Escalation 流程

8. **[测试和回归策略](./07_test_and_regression_strategy.md)** ✅ **已完成**
   - 测试分层策略（Smoke/Nightly/Weekly）
   - 测试选择原则
   - Coverage 目标和收集方法
   - Testlist 维护规范

9. **[Runner 和 License 检查清单](./08_runner_and_license_checklist.md)** ✅ **已完成**
   - Self-hosted runner 环境要求
   - License 配置和验证
   - 工具版本锁定策略
   - 故障排查命令集

10. **[术语表](./09_glossary.md)** ✅ **已完成**
   - CI 术语中英文对照
   - CVA6 特定术语解释
   - 工具和命令速查

---

## 🎯 按使用场景查找

### 场景 1：我是新人，想了解 CVA6 的 CI 系统

**推荐路径**：
1. 阅读 [01_ci_for_beginners.md](./01_ci_for_beginners.md)（15-20 分钟）
2. 阅读 [WEEK1_EXECUTION_GUIDE.md](./WEEK1_EXECUTION_GUIDE.md)（30-40 分钟）⭐
3. 按照执行指南配置环境并运行 smoke test（1-2 小时）
4. 浏览 [02_current_cva6_ci_inventory.md](./02_current_cva6_ci_inventory.md) 了解全貌

### 场景 2：我要提交 PR，想知道 CI 会运行什么测试

**快速查阅**：
- GitHub Actions 测试矩阵：见 [02_current_cva6_ci_inventory.md § 1.2](./02_current_cva6_ci_inventory.md#12-github-actions-配置)
- Smoke test 内容：见 [01_ci_for_beginners.md § 2.1](./01_ci_for_beginners.md#21-测试分层-test-pyramid)
- 预计运行时间：30-40 分钟
- 失败排查：见 [01_ci_for_beginners.md § 4](./01_ci_for_beginners.md#四常见-ci-失败类型和排查路径)

### 场景 3：CI 失败了，我不知道怎么办

**故障排查步骤**：
1. 查看 [01_ci_for_beginners.md § 4.1](./01_ci_for_beginners.md#41-失败分类决策树)（失败分类决策树）
2. 根据错误类型查找对应的解决方案：见 [§ 4.2](./01_ci_for_beginners.md#42-常见错误和解决方案)
3. 如果问题仍未解决，查看 [06_ci_triage_playbook.md](./06_ci_triage_playbook.md)（完整故障排查手册）
4. 联系 CI 维护者或在仓库提 issue

### 场景 4：我想添加新的测试到 CI

**操作指南**：
1. 了解测试分层：见 [01_ci_for_beginners.md § 2.1](./01_ci_for_beginners.md#21-测试分层-test-pyramid)
2. 选择合适的 testlist：见 [02_current_cva6_ci_inventory.md § 3.1](./02_current_cva6_ci_inventory.md#31-testlist-文件组织)
3. 添加测试并验证：详见 [07_test_and_regression_strategy.md](./07_test_and_regression_strategy.md)（测试和回归策略）
4. 提交 PR 并等待 CI 验证

### 场景 5：我要搭建自己的 CI 环境（DSim/Questa）

**搭建指南**：
1. 准备工作：见 [02_current_cva6_ci_inventory.md § 4](./02_current_cva6_ci_inventory.md#四仿真环境和工具链)
2. 环境配置：见 [08_runner_and_license_checklist.md](./08_runner_and_license_checklist.md)（Runner 和 License 检查清单）
3. 集成步骤：参考 Week 3-4 执行计划（见 `/home/junchao/.claude/plans/gleaming-whistling-waterfall.md`）

---

## 🛠️ 快速命令参考

### 环境配置

```bash
# 一键配置
cd docs/ci
bash setup-local-env.sh

# 或手动配置
export RISCV=/path/to/riscv-toolchain
export NUM_JOBS=8
source verif/sim/setup-env.sh
```

### 运行测试

```bash
# Smoke test（快速验证）
cd verif/sim
DV_SIMULATORS=veri-testharness,spike \
DV_TARGET=cv64a6_imafdc_sv39 \
bash ../regress/smoke-tests-cv64a6_imafdc_sv39.sh

# 单个测试
python3 cva6.py \
  --target cv64a6_imafdc_sv39 \
  --iss veri-testharness,spike \
  --test rv64ui-p-add

# 完整回归
bash ../regress/dv-riscv-arch-test.sh
```

### 查看结果

```bash
# 测试日志
tail -100 verif/sim/logfile.log

# 波形（如果启用 TRACE）
gtkwave verif/sim/trace_hart_0000.fst
```

---

## 📊 CI 系统概览

### 当前状态

**GitLab CI（Thales 内网）**：
- ✅ 完整回归系统（Smoke + Nightly + Weekly）
- ✅ 支持多种仿真器（Verilator, VCS, Questa, Xcelium）
- ✅ Coverage 收集和报告
- ✅ Dashboard 和报告系统
- ❌ 仅内网可访问

**GitHub Actions（公开）**：
- ✅ PR-level smoke test（30-40 分钟）
- ✅ 支持 Verilator + Spike
- ✅ 社区友好
- ❌ 无 coverage 收集
- ❌ 测试覆盖有限

### 目标状态（6-8 周计划）

**Phase 1 (Week 1-2)**：Verilator + 文档
- ✅ 本地环境搭建脚本 (setup-local-env.sh) ✓ **已完成**
- ✅ CI 入门文档 (01_ci_for_beginners.md) ✓ **已完成**
- ✅ 现状清单文档 (02_current_cva6_ci_inventory.md) ✓ **已完成**
- ✅ Week 1 执行指南 (WEEK1_EXECUTION_GUIDE.md) ✓ **已完成**
- ⏳ 本地 smoke test 验证（待用户执行）
- ⏳ GitHub Actions PR-level CI 优化

**Phase 2 (Week 3-4)**：DSim + QuestaSim 集成
- ⏳ DSim APU testbench 集成
- ⏳ QuestaSim APU testbench 集成
- ⏳ 测试矩阵扩展

**Phase 3 (Week 5-6)**：Regression + Coverage
- ⏳ Weekly regression 框架
- ⏳ Coverage 收集和报告
- ⏳ Dashboard 集成

---

## 🤝 贡献和反馈

### 文档维护

这些文档由 OpenHW Group CVA6 CI 团队维护。如有问题或建议：

1. **报告问题**：在 CVA6 仓库提 issue
2. **建议改进**：提交 PR 或在 issue 中讨论
3. **联系维护者**：通过 OpenHW 邮件列表或 Slack

### 更新记录

| 日期 | 版本 | 更新内容 | 作者 |
|------|------|---------|------|
| 2026-01-18 | v3.0 | **重大调整**: 优先级重排，CI优先 | CI Team |
| | | - 执行计划v3.0: 6周核心交付 | |
| | | - 创建文件夹结构（plans/reports/guides/）| |
| | | - Week 1-2: GitHub Actions PR CI（原Week 4）| |
| | | - Week 3-4: QuestaSim完整集成 | |
| | | - Week 5-6: Weekly Regression + 报告网站 ✅ | |
| | | - Week 7-12: DSim集成（可选）+ 优化 | |
| 2026-01-18 | v1.1 | 完成核心CI文档（Week 2-6 交付）| CI Team |
| | | - 03_how_ci_runs_end_to_end.md (956行) | |
| | | - 05_ci_contract.md (493行) | |
| | | - 06_ci_triage_playbook.md (868行) | |
| | | - 07_test_and_regression_strategy.md (777行) | |
| | | - 08_runner_and_license_checklist.md (777行) | |
| | | - 09_glossary.md (888行) | |
| 2026-01-17 | v1.0 | 创建初始文档框架（Week 1 交付）| CI Team |
| | | - 01_ci_for_beginners.md (648行) | |
| | | - 02_current_cva6_ci_inventory.md (846行) | |
| | | - setup-local-env.sh | |
| | | - guides/WEEK1_EXECUTION_GUIDE.md (529行) | |
| | | - 00_README.md | |

---

## 📞 获取帮助

### 常见问题

**Q: 我应该从哪里开始？**
A: 从 [01_ci_for_beginners.md](./01_ci_for_beginners.md) 开始，然后运行 `setup-local-env.sh`。

**Q: 文档太多了，我只想快速跑一个测试**
A: 运行以下命令：
```bash
cd docs/ci
bash setup-local-env.sh
# 按提示操作，选择运行快速测试
```

**Q: 我修改了代码，如何确保不会破坏 CI？**
A: 在本地运行 smoke test：
```bash
cd verif/sim
DV_SIMULATORS=veri-testharness,spike \
bash ../regress/smoke-tests-cv64a6_imafdc_sv39.sh
```

**Q: 我想了解 CI 的详细执行流程**
A: 查看 [03_how_ci_runs_end_to_end.md](./03_how_ci_runs_end_to_end.md)

### 联系方式

- **GitHub Issues**: https://github.com/openhwgroup/cva6/issues
- **OpenHW Group**: https://www.openhwgroup.org/
- **邮件列表**: cva6@lists.openhwgroup.org

---

## 📝 许可证

本文档遵循 CVA6 项目的许可证：

- **代码**：Solderpad Hardware Licence, Version 2.0
- **文档**：Apache-2.0 WITH SHL-2.0

详见：https://solderpad.org/licenses/

---

**祝您使用愉快！如有问题，请随时联系我们。** 🎉
