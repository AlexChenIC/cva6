# CI 契约（CI Contract）

**文档版本**: v1.0
**创建日期**: 2026-01-18
**维护者**: OpenHW CI Team
**目标读者**: 所有 CVA6 贡献者、CI 维护者、项目管理者

---

## 文档目的

本文档定义 **CVA6 CI 系统的边界和承诺**，明确：
- ✅ CI **保证什么**（Guarantees）
- ❌ CI **不保证什么**（Non-Guarantees）
- 📊 CI **服务等级协议**（SLA）
- 🔧 CI **失败处理策略**（Failure Handling）

---

## 目录

1. [CI 保证什么](#一ci-保证什么)
2. [CI 不保证什么](#二ci-不保证什么)
3. [SLA 定义](#三sla-定义)
4. [失败处理策略](#四失败处理策略)
5. [用户责任](#五用户责任)
6. [CI 维护者责任](#六ci-维护者责任)

---

## 一、CI 保证什么

### 1.1 功能正确性保证

#### ✅ CI PASS 代表什么

当 CI pipeline 显示 **绿色（PASS）** 时，保证以下内容：

| 保证项 | 具体内容 | 覆盖范围 |
|--------|----------|----------|
| **基础功能正确** | 所有 smoke test 通过 | 6-10 个核心测试 |
| **ISA 合规** | RISC-V 架构测试通过 | riscv-arch-test 套件 |
| **RTL 仿真一致** | Verilator/Spike 结果匹配 | Tandem simulation |
| **编译无错误** | RTL lint clean, 综合无错误 | Verilator lint, Synopsys |
| **回归无破坏** | 历史通过的测试仍然通过 | Regression test suite |

#### 示例

```
✅ CI PASS = 以下保证成立:
   - rv64ui-p-add (基础整数运算) ✓
   - rv64um-p-mul (乘法扩展) ✓
   - rv64ua-p-amoadd (原子操作) ✓
   - rv64mi-p-csr (CSR 访问) ✓
   - riscv-arch-test 核心集合 ✓
   - Verilator ↔ Spike 100% 匹配 ✓
```

---

### 1.2 测试覆盖保证

#### PR-level CI（GitHub Actions）

| 测试类型 | 数量 | 覆盖的功能 |
|----------|------|------------|
| **Smoke tests** | ~10 | 基础 ALU、Load/Store、Branch |
| **ISA tests** | ~800 | RV64I/M/A/F/D/C 基础指令集 |
| **Config tests** | 4 | HPDCache, Write-back cache 配置 |

**保证**: PR merge 前这些测试 100% 通过

---

#### Nightly/Weekly CI（GitLab）

| 测试类型 | 数量 | 覆盖的功能 |
|----------|------|------------|
| **完整 ISA 测试** | ~1200 | 所有 RISC-V 指令（含特权模式）|
| **随机测试** | ~500 | riscv-dv 生成的随机程序 |
| **Benchmark** | ~10 | CoreMark, Dhrystone, 实际程序 |
| **UVM 测试** | ~200 | 随机约束、功能覆盖 |

**保证**: Weekly regression 覆盖率 >90%（代码行覆盖率）

---

### 1.3 性能保证

#### CI 运行时间 SLA

| CI 类型 | 目标时间 | 最大时间 | 超时处理 |
|---------|----------|----------|----------|
| **PR Smoke test** | 20-25 分钟 | 40 分钟 | 自动取消 |
| **Nightly regression** | 4-6 小时 | 8 小时 | 告警通知 |
| **Weekly full** | 8-12 小时 | 24 小时 | 告警通知 |

**保证**: 95% 的 CI runs 在目标时间内完成

---

### 1.4 可用性保证

#### CI 系统可用性

| 指标 | 目标 | 测量方式 |
|------|------|----------|
| **Uptime** | 99% | GitLab/GitHub 状态监控 |
| **Queue 时间** | <5 分钟 | Runner 排队时间 |
| **成功率** | >95% | (PASS / Total runs) |

**保证**: CI 系统在工作时间（周一至周五）持续可用

---

## 二、CI 不保证什么

### 2.1 功能边界

#### ❌ CI 不验证的内容

| 不保证项 | 说明 | 原因 |
|----------|------|------|
| **所有 Corner Cases** | 极端边界条件 | 测试集有限 |
| **所有 RTL Bugs** | RTL 代码中的所有缺陷 | 覆盖率未达 100% |
| **系统级集成** | Linux boot, 多核同步 | 超出 CI 范围 |
| **FPGA/ASIC 正确性** | 物理实现的功能 | 需要物理验证 |
| **第三方 IP 问题** | AXI, APB 等 IP 的 bug | 非 CVA6 代码 |
| **工具链 Bug** | GCC, Verilator 的缺陷 | 外部依赖 |

#### 示例

```
❌ CI PASS ≠ 以下保证:
   - 所有 PMP 配置组合都正确 ✗
   - FPU 处理所有 NaN 场景 ✗
   - 多核 coherency 无死锁 ✗
   - FPGA 综合后功能正确 ✗
```

---

### 2.2 覆盖率边界

#### 当前覆盖率（Weekly Regression）

| 覆盖率类型 | 当前值 | 目标值 | 差距 |
|------------|--------|--------|------|
| **Line Coverage** | ~92% | 95% | 3% |
| **Branch Coverage** | ~88% | 90% | 2% |
| **FSM Coverage** | ~95% | 98% | 3% |
| **Toggle Coverage** | ~85% | N/A | - |
| **Functional Coverage** | ~70% | 85% | 15% |

**不保证**: 未覆盖的 8-12% 代码路径一定正确

---

### 2.3 性能边界

#### ❌ CI 不保证的性能指标

- **Timing Closure**: CI 不验证 ASIC/FPGA timing
- **Power Consumption**: CI 不测量功耗
- **PPA (Performance, Power, Area)**: CI 只做功能验证

**说明**: 这些指标需要专门的后端验证流程

---

## 三、SLA 定义

### 3.1 CI 运行时间 SLA

#### 详细 SLA 表

| CI 类型 | P50 (中位数) | P95 | P99 | 超时阈值 |
|---------|--------------|-----|-----|----------|
| **PR Smoke (GitHub)** | 22 min | 30 min | 35 min | 40 min |
| **PR Smoke (GitLab)** | 25 min | 35 min | 40 min | 45 min |
| **Nightly Regression** | 5 hr | 7 hr | 7.5 hr | 8 hr |
| **Weekly Full** | 10 hr | 18 hr | 22 hr | 24 hr |

**承诺**:
- 95% 的 runs 在 P95 时间内完成
- 超过超时阈值的 run 自动取消并通知

---

### 3.2 CI 成功率 SLA

#### 目标成功率

| CI 类型 | 目标成功率 | 当前成功率 | 状态 |
|---------|-----------|-----------|------|
| **PR Smoke** | >95% | 97% | ✅ 达标 |
| **Nightly Regression** | >90% | 88% | ⚠️ 接近 |
| **Weekly Full** | >85% | 82% | ⚠️ 需改进 |

**定义**:
- 成功 = 所有必需测试通过（允许少量已知失败）
- 失败 = 新引入的测试失败或基础设施问题

---

### 3.3 CI 响应时间 SLA

#### Issue 响应时间

| 问题类型 | 首次响应 | 解决时间 | 责任人 |
|----------|----------|----------|--------|
| **CI 完全不可用** | 1 小时 | 4 小时 | CI 维护者 |
| **个别测试失败** | 4 小时 | 2 天 | 代码作者 + CI |
| **性能问题（超时）** | 1 天 | 1 周 | CI 维护者 |
| **新功能请求** | 1 周 | 1 月 | CI 维护者 |

---

### 3.4 Runner 可用性 SLA

#### Self-hosted Runner

| 指标 | 目标 | 测量方式 |
|------|------|----------|
| **可用性** | 99% | Uptime 监控 |
| **最大 Queue 时间** | 5 分钟 | GitLab/GitHub metrics |
| **并发能力** | ≥10 jobs | Runner 配置 |

**承诺**: 工作时间（9:00-18:00 UTC+8）runner 可用性 99.5%

---

## 四、失败处理策略

### 4.1 CI 失败分类

#### 失败类型决策树

```
CI 失败
  │
  ├─ Infra 失败 (基础设施)
  │   ├─ Runner 离线 → CI 维护者修复，不阻塞 PR
  │   ├─ Network timeout → 自动重试 3 次
  │   ├─ License 超限 → CI 维护者增加 license
  │   └─ 磁盘空间不足 → 自动清理 + 告警
  │
  ├─ Tool 失败 (工具问题)
  │   ├─ Verilator crash → 报告 Verilator 社区
  │   ├─ GCC bug → 提交 GCC bug report
  │   └─ Spike 不匹配 → 检查 Spike 版本
  │
  └─ RTL 失败 (真实 bug)
      ├─ 新测试失败 → 代码作者修复
      ├─ Regression 失败 → 立即回滚或修复
      └─ Coverage 下降 → Review 并添加测试
```

---

### 4.2 失败优先级

| 优先级 | 类型 | SLA | 示例 |
|--------|------|-----|------|
| **P0 (Critical)** | 所有 PR CI 失败 | 1 小时修复 | Runner 全部离线 |
| **P1 (High)** | Master 分支 CI 失败 | 4 小时修复 | RTL 引入重大 bug |
| **P2 (Medium)** | Nightly CI 失败 | 1 天修复 | 单个测试 timeout |
| **P3 (Low)** | Weekly CI 部分失败 | 1 周修复 | 非关键测试失败 |

---

### 4.3 失败处理流程

#### Step-by-Step 流程

```
1. CI 失败通知
   ↓
2. 分类（Infra / Tool / RTL）
   ↓
3. 判断优先级（P0-P3）
   ↓
4. 分配责任人
   │  ├─ Infra → CI 维护者
   │  ├─ Tool → CI 维护者 + 工具支持
   │  └─ RTL → 代码作者
   ↓
5. 修复验证
   │  ├─ 本地复现
   │  ├─ 修复代码
   │  └─ CI 验证通过
   ↓
6. 根因分析（RCA）
   │  ├─ 记录失败原因
   │  ├─ 添加测试覆盖
   │  └─ 更新文档
   ↓
7. 关闭 Issue
```

---

### 4.4 已知失败 (Known Failures)

#### 已知失败列表管理

CVA6 维护一个 **已知失败列表** (`known_failures.yaml`)：

```yaml
# known_failures.yaml

- test: rv64ua-p-amoadd_w
  status: flaky
  reason: "Timing issue in VCS simulation"
  bug_id: CVA6-1234
  expected_fix: "2026-02"

- test: rv64mi-p-illegal
  status: expected_fail
  reason: "Feature not implemented (Hypervisor extension)"
  bug_id: N/A
  expected_fix: "2026-Q3"
```

**策略**:
- ✅ 已知失败的测试 = CI 仍然 PASS（标记为 XFAIL）
- ❌ 新的失败测试 = CI FAIL（阻塞 PR）
- ⚠️ 已知失败突然 PASS = 通知 CI 维护者（可能修复了）

---

## 五、用户责任

### 5.1 PR 提交者的责任

在提交 PR 时，**用户应该**：

| 责任 | 具体内容 | 如何验证 |
|------|----------|----------|
| **本地测试** | 运行 smoke test | `bash verif/regress/smoke-tests-*.sh` |
| **代码质量** | 通过 lint 检查 | `verilator --lint-only` |
| **测试添加** | 新功能需要新测试 | 添加到 `testlist_*.yaml` |
| **文档更新** | API 变更需要更新文档 | `docs/` 目录 |
| **CI 通过** | PR CI 必须绿色 | GitHub Actions 状态 |

**承诺**: 用户不应该依赖 CI 发现明显的编译错误或 lint 问题

---

### 5.2 用户不应该做什么

| 不应该做的事 | 原因 | 正确做法 |
|--------------|------|----------|
| **绕过 CI** | 破坏质量保证 | 等待 CI 通过 |
| **频繁 force push** | 浪费 CI 资源 | 本地验证后再 push |
| **提交未测试代码** | 引入明显 bug | 本地运行 smoke test |
| **忽略 CI 失败** | 累积技术债 | 修复后再 merge |

---

## 六、CI 维护者责任

### 6.1 CI 维护者的承诺

CI 维护者**应该**：

| 责任 | 具体内容 | 时间承诺 |
|------|----------|----------|
| **系统可用性** | 保证 CI 系统运行 | 99% uptime |
| **性能优化** | 持续优化 CI 速度 | 季度审查 |
| **问题响应** | 及时响应 CI 问题 | 见 SLA (§3.3) |
| **文档维护** | 更新 CI 文档 | 每次重大变更 |
| **工具更新** | 定期更新工具链 | 每季度 |

---

### 6.2 CI 维护者不负责什么

| 不负责项 | 说明 | 责任人 |
|----------|------|--------|
| **RTL Bug 修复** | CI 只检测，不修复 | 代码作者 |
| **测试编写** | 新功能的测试 | Feature 开发者 |
| **工具 Bug** | Verilator, Spike bug | 工具社区 |
| **硬件调试** | FPGA/ASIC 问题 | 硬件团队 |

---

## 七、CI 演进计划

### 7.1 短期改进（2026 Q1-Q2）

| 改进项 | 目标 | 预期效果 |
|--------|------|----------|
| **DSim/Questa 集成** | 支持商业仿真器 | 提高仿真速度 50% |
| **Coverage 提升** | Line coverage >95% | 发现更多 corner case |
| **GitHub Actions 增强** | PR-level coverage 报告 | 提高 PR 质量 |

---

### 7.2 中期改进（2026 Q3-Q4）

| 改进项 | 目标 | 预期效果 |
|--------|------|----------|
| **UVM Testbench 扩展** | Functional coverage >85% | 提高验证完整性 |
| **Dashboard 集成** | 实时 CI 状态监控 | 提高透明度 |
| **Smart Test Selection** | 增量测试 | 减少 CI 时间 75% |

---

### 7.3 长期改进（2027+）

| 改进项 | 目标 | 预期效果 |
|--------|------|----------|
| **FPGA 原型验证** | CI 集成 FPGA 测试 | 接近真实环境 |
| **Silicon Validation** | Tapeout 前完整验证 | 降低流片风险 |
| **ML-based Debugging** | AI 辅助故障诊断 | 减少 debug 时间 |

---

## 八、契约变更流程

### 8.1 如何修改本契约

本契约的修改需要以下流程：

```
1. 提出修改建议
   ↓
2. CI 维护者 review
   ↓
3. 社区讨论（GitHub Issue）
   ↓
4. 投票表决（需 2/3 同意）
   ↓
5. 更新文档
   ↓
6. 公告通知（邮件列表 + Slack）
```

---

### 8.2 契约版本历史

| 版本 | 日期 | 主要变更 | 作者 |
|------|------|----------|------|
| v1.0 | 2026-01-18 | 初始版本 | CI Team |

---

## 九、总结

### 9.1 关键要点

**CI 保证**:
- ✅ 基础功能正确（ISA 合规 + Tandem simulation）
- ✅ 回归测试无破坏
- ✅ 95% 的 runs 在 SLA 时间内完成

**CI 不保证**:
- ❌ 所有 corner cases 覆盖
- ❌ 100% 代码覆盖率
- ❌ FPGA/ASIC 实现正确性

**SLA**:
- PR Smoke: <30 分钟（P95）
- Nightly: <7 小时（P95）
- 成功率: >95%（PR）

---

### 9.2 如何使用本契约

**对于 PR 提交者**:
1. 理解 CI PASS 的含义
2. 遵守用户责任（§5）
3. CI 失败时参考失败处理流程（§4）

**对于 CI 维护者**:
1. 遵守 SLA 承诺（§3）
2. 及时响应问题（§6）
3. 持续改进 CI 系统（§7）

**对于项目管理者**:
1. 将本契约作为质量标准
2. 监控 SLA 达成情况
3. 支持 CI 改进计划

---

**相关文档**:
- [01_ci_for_beginners.md](./01_ci_for_beginners.md) - CI 基础概念
- [03_how_ci_runs_end_to_end.md](./03_how_ci_runs_end_to_end.md) - CI 执行流程
- [06_ci_triage_playbook.md](./06_ci_triage_playbook.md) - 故障排查手册
