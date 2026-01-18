# CVA6 CI 文档结构说明

**最后更新**: 2026-01-18

---

## 📁 文件夹结构

```
docs/ci/
├── README_STRUCTURE.md          # 本文件 - 文档结构说明
├── 00_README.md                 # CI文档中心主入口 ⭐ 从这里开始
│
├── Core Documentation (核心文档) - 按序阅读
│   ├── 01_ci_for_beginners.md                  # CI入门指南
│   ├── 02_current_cva6_ci_inventory.md         # 当前CI系统清单
│   ├── 03_how_ci_runs_end_to_end.md            # CI端到端流程
│   ├── 05_ci_contract.md                       # CI契约
│   ├── 06_ci_triage_playbook.md                # CI故障排查手册
│   ├── 07_test_and_regression_strategy.md      # 测试和回归策略
│   ├── 08_runner_and_license_checklist.md      # Runner和License清单
│   └── 09_glossary.md                          # 术语表
│
├── setup-local-env.sh           # 一键环境配置脚本
│
├── plans/                       # 执行计划
│   └── gleaming-whistling-waterfall.md         # CVA6 CI能力建设执行计划 (v3.0)
│
├── reports/                     # 分析报告
│   ├── TASK_ANALYSIS_REGRESSION_CAPABILITY.md  # 任务分析报告
│   └── DOCUMENTATION_REVIEW_REPORT.md          # 文档审查报告
│
└── guides/                      # 执行指南
    ├── WEEK1_EXECUTION_GUIDE.md                # Week 1 执行指南
    └── WEEK1_DELIVERY_SUMMARY.md               # Week 1 交付总结
```

---

## 🎯 快速导航

### 新手入门（第一次使用）
1. **从这里开始** → [`00_README.md`](./00_README.md)
2. **了解CI基础** → [`01_ci_for_beginners.md`](./01_ci_for_beginners.md)
3. **运行第一个测试** → [`guides/WEEK1_EXECUTION_GUIDE.md`](./guides/WEEK1_EXECUTION_GUIDE.md)
4. **配置环境** → [`setup-local-env.sh`](./setup-local-env.sh)

### 项目规划（领导/管理层）
1. **执行计划** → [`plans/gleaming-whistling-waterfall.md`](./plans/gleaming-whistling-waterfall.md) ⭐⭐⭐
   - v3.0版本：CI优先，6周核心交付
   - 包含明天汇报要点（10张幻灯片）
2. **任务分析** → [`reports/TASK_ANALYSIS_REGRESSION_CAPABILITY.md`](./reports/TASK_ANALYSIS_REGRESSION_CAPABILITY.md)
3. **现状清单** → [`02_current_cva6_ci_inventory.md`](./02_current_cva6_ci_inventory.md)

### CI运维（开发者）
1. **CI运行流程** → [`03_how_ci_runs_end_to_end.md`](./03_how_ci_runs_end_to_end.md)
2. **故障排查** → [`06_ci_triage_playbook.md`](./06_ci_triage_playbook.md)
3. **测试策略** → [`07_test_and_regression_strategy.md`](./07_test_and_regression_strategy.md)
4. **Runner配置** → [`08_runner_and_license_checklist.md`](./08_runner_and_license_checklist.md)

### PR提交（贡献者）
1. **CI保证什么** → [`05_ci_contract.md`](./05_ci_contract.md)
2. **常见问题** → [`06_ci_triage_playbook.md`](./06_ci_triage_playbook.md)
3. **测试清单** → [`02_current_cva6_ci_inventory.md`](./02_current_cva6_ci_inventory.md)

---

## 📊 文档版本

| 文件 | 版本 | 更新日期 | 状态 |
|------|------|---------|------|
| `plans/gleaming-whistling-waterfall.md` | v3.0 | 2026-01-18 | ✅ 最新（CI优先版） |
| 核心文档 (01-09) | v1.1 | 2026-01-18 | ✅ 完成 |
| `guides/WEEK1_EXECUTION_GUIDE.md` | v1.0 | 2026-01-17 | ✅ 完成 |
| `reports/TASK_ANALYSIS_REGRESSION_CAPABILITY.md` | v1.0 | 2026-01-18 | ✅ 完成 |

---

## 🔄 版本历史

### v3.0 (2026-01-18) - CI优先版
- **重大调整**：优先级重排，CI能力优先，DSim降为次要
- **核心改进**：
  - Week 1-2: GitHub Actions PR CI上线（原Week 4）
  - Week 3-4: QuestaSim完整集成（原Week 5）
  - Week 5-6: Weekly Regression + 报告网站（核心交付完成）
  - Week 7-12: DSim集成（可选）+ 优化
- **明天汇报要点**：10张幻灯片，强调6周完成核心CI能力
- **风险降低**：核心交付不依赖DSim，技术可行性 95%

### v2.0 (2026-01-18)
- 基于实际环境状态更新（Verilator/Spike/Questa已安装）
- 12周执行计划
- 明天汇报材料

### v1.1 (2026-01-18)
- 完成核心CI文档（03, 05, 06, 07, 08, 09）
- 修复 00_README.md 中的过时引用

### v1.0 (2026-01-17)
- 初始文档框架（01, 02, setup-local-env.sh, WEEK1_EXECUTION_GUIDE.md）

---

## 📞 获取帮助

- **GitHub Issues**: https://github.com/openhwgroup/cva6/issues
- **OpenHW Group**: https://www.openhwgroup.org/
- **邮件列表**: cva6@lists.openhwgroup.org

---

## 💡 提示

**明天汇报重点文件**：
- [`plans/gleaming-whistling-waterfall.md`](./plans/gleaming-whistling-waterfall.md) - 第三部分"明天汇报要点"
- 核心信息：**6周完成核心CI能力，DSim作为可选扩展**

**立即可用资源**：
- Verilator ✅ 已验证
- QuestaSim ✅ 已安装
- Spike ✅ 已验证
- GitHub Actions ✅ 有参考配置

**下一步行动**（批准后）：
1. Day 1: 验证 Verilator + Spike baseline
2. Day 2: 设计 GitHub Actions workflow
3. Day 3: 配置 self-hosted runner
4. Day 4: 创建 PR workflow 初版
5. Day 5: 本地测试和文档

---

**文档维护者**: OpenHW CVA6 CI Team
**许可证**: Apache-2.0 WITH SHL-2.0
