# CI 故障排查手册（CI Triage Playbook）

**文档版本**: v1.0
**创建日期**: 2026-01-18
**维护者**: OpenHW CI Team
**目标读者**: 所有遇到 CI 失败的用户、CI 维护者

---

## 文档目的

本手册提供 **系统化的 CI 故障排查流程**，帮助您：
- 🔍 快速定位 CI 失败根因
- 🛠️ 自助解决常见问题
- 📞 知道何时升级到 CI 维护者

---

## 目录

1. [快速诊断流程](#一快速诊断流程)
2. [失败分类决策树](#二失败分类决策树)
3. [常见问题和解决方案](#三常见问题和解决方案)
4. [高级故障排查](#四高级故障排查)
5. [Escalation 流程](#五escalation-流程)
6. [故障排查工具箱](#六故障排查工具箱)

---

## 一、快速诊断流程

### 1.1 5 分钟快速检查清单

当 CI 失败时，按以下顺序检查（**5 分钟内完成**）：

```
[ ] Step 1: 查看 CI 状态页面
    GitHub: https://github.com/openhwgroup/cva6/actions
    GitLab: https://gitlab.com/.../cva6/pipelines

[ ] Step 2: 找到失败的 Job
    点击红色 ❌ 的 job，查看日志

[ ] Step 3: 检查错误类型（跳到日志最后 100 行）
    - 是否有 "ERROR:", "FAIL:", "Traceback"？
    - 是否有 timeout 提示？

[ ] Step 4: 快速分类（见 § 2.1）
    - 环境问题？（工具未找到）
    - 编译问题？（语法错误）
    - 仿真问题？（测试失败）
    - 基础设施问题？（runner 离线）

[ ] Step 5: 查找对应解决方案（见 § 3）
```

---

### 1.2 快速诊断命令

**GitHub Actions**:
```bash
# 下载失败 job 的日志
gh run view <run-id> --log-failed > failed.log

# 查看最后 100 行
tail -100 failed.log

# 搜索错误关键词
grep -E "ERROR|FAIL|Traceback" failed.log
```

**GitLab CI**:
```bash
# 下载失败 job 的日志（需要 GitLab CLI）
glab ci trace <job-id> > failed.log

# 或直接在 Web UI 查看
```

---

## 二、失败分类决策树

### 2.1 顶层决策树

```
CI 失败
  │
  ├─ 在哪个阶段失败？
  │   ├─ Setup/Build 阶段 → [§ 2.2 环境问题]
  │   ├─ Test 阶段 → [§ 2.3 测试问题]
  │   ├─ Report 阶段 → [§ 2.4 报告问题]
  │   └─ Timeout → [§ 2.5 超时问题]
  │
  ├─ 是否所有 Jobs 都失败？
  │   ├─ 是 → [§ 3.1 基础设施问题]
  │   └─ 否 → [§ 3.2 特定 Job 问题]
  │
  └─ 是否第一次失败？
      ├─ 是 → [§ 3.3 新引入问题]
      └─ 否 → [§ 3.4 间歇性问题]
```

---

### 2.2 环境问题决策树

```
Setup/Build 失败
  │
  ├─ 错误信息包含 "command not found"？
  │   ├─ 是 → 工具未安装或 PATH 未设置
  │   │      解决: 检查环境变量（见 § 3.1.1）
  │   └─ 否 → 继续
  │
  ├─ 错误信息包含 "No such file or directory"？
  │   ├─ 是 → 文件缺失或路径错误
  │   │      解决: 检查 git submodule（见 § 3.1.2）
  │   └─ 否 → 继续
  │
  ├─ 错误信息包含 "Permission denied"？
  │   ├─ 是 → 文件权限问题
  │   │      解决: chmod +x 或检查 runner 权限
  │   └─ 否 → 继续
  │
  └─ 错误信息包含 "Disk quota exceeded"？
      ├─ 是 → 磁盘空间不足
      │      解决: 清理临时文件（见 § 3.1.3）
      └─ 否 → 升级到 CI 维护者
```

---

### 2.3 测试问题决策树

```
Test 失败
  │
  ├─ 多少测试失败？
  │   ├─ 所有测试 (100%) → RTL 编译失败或环境问题
  │   ├─ 大部分 (>50%) → 重大 RTL bug
  │   ├─ 少数 (<10%) → 特定功能回归
  │   └─ 1 个测试 → 可能是 flaky test
  │
  ├─ 错误信息是什么？
  │   ├─ "Mismatch between RTL and ISS" → RTL 功能错误（见 § 3.2.1）
  │   ├─ "Timeout" → 测试卡住或运行太慢（见 § 3.2.2）
  │   ├─ "Assertion failed" → RTL assertion 触发（见 § 3.2.3）
  │   ├─ "Segmentation fault" → 仿真器 crash（见 § 3.2.4）
  │   └─ 其他 → 继续分析
  │
  └─ 是否是新测试？
      ├─ 是 → 新测试可能有问题
      └─ 否 → RTL 回归（需要 bisect）
```

---

### 2.4 报告问题决策树

```
Report 阶段失败
  │
  ├─ 错误信息包含 "Permission denied"？
  │   ├─ 是 → Artifact 上传权限问题
  │   │      解决: 检查 GitLab/GitHub token
  │   └─ 否 → 继续
  │
  ├─ 错误信息包含 "ModuleNotFoundError"？
  │   ├─ 是 → Python 脚本缺少依赖
  │   │      解决: pip install 缺少的模块
  │   └─ 否 → 继续
  │
  └─ 错误信息包含 "vcover: command not found"？
      ├─ 是 → Coverage 工具未安装
      │      解决: 安装 Questa 或 VCS
      └─ 否 → 升级到 CI 维护者
```

---

### 2.5 超时问题决策树

```
Timeout 失败
  │
  ├─ 哪个阶段超时？
  │   ├─ Build 阶段 → 编译太慢（见 § 3.3.1）
  │   ├─ Test 阶段 → 仿真太慢（见 § 3.3.2）
  │   └─ Report 阶段 → 报告生成太慢（见 § 3.3.3）
  │
  ├─ 是否每次都超时？
  │   ├─ 是 → 系统性能能问题
  │   │      解决: 增加超时时间或优化测试
  │   └─ 否 → Runner 负载高
  │          解决: 等待重试或增加 runner
  │
  └─ 超时时间是多少？
      ├─ < 1 小时 → 可能是网络问题
      ├─ 1-4 小时 → 正常范围，可能需要优化
      └─ > 4 小时 → 检查是否有死循环
```

---

## 三、常见问题和解决方案

### 3.1 环境和基础设施问题

#### 3.1.1 工具未找到（command not found）

**症状**:
```
ERROR: verilator: command not found
ERROR: spike: command not found
ERROR: riscv64-unknown-elf-gcc: command not found
```

**根因**: 环境变量未设置或工具未安装

**解决方案**:

```bash
# 检查工具是否安装
which verilator
which spike
which $RISCV/bin/riscv64-unknown-elf-gcc

# 如果未找到，设置环境变量
export VERILATOR_INSTALL_DIR=/path/to/verilator
export SPIKE_INSTALL_DIR=/path/to/spike
export RISCV=/path/to/riscv-toolchain
export PATH=$VERILATOR_INSTALL_DIR/bin:$SPIKE_INSTALL_DIR/bin:$RISCV/bin:$PATH

# 或运行环境配置脚本
source verif/sim/setup-env.sh
```

**预防措施**: 使用 `docs/ci/setup-local-env.sh` 自动配置环境

---

#### 3.1.2 文件或目录不存在

**症状**:
```
FileNotFoundError: [Errno 2] No such file or directory: 'verif/core-v-verif/...'
fatal: pathspec 'verif/tests/riscv-tests' did not match any files
```

**根因**: Git submodule 未初始化

**解决方案**:

```bash
# 初始化所有 submodules
git submodule update --init --recursive

# 验证 submodules 状态
git submodule status

# 应该看到：
# 60e57248... verif/core-v-verif (22dc5fc-2958-g60e57248)
# （没有 - 前缀表示已初始化）
```

**预防措施**: 在 CI 脚本中总是包含 `git submodule update --init --recursive`

---

#### 3.1.3 磁盘空间不足

**症状**:
```
ERROR: No space left on device
Disk quota exceeded
```

**根因**: 临时文件、artifacts 或 cache 占满磁盘

**解决方案**:

```bash
# 检查磁盘使用情况
df -h

# 清理 CVA6 临时文件
make -C verif/sim clean_all
make clean
rm -rf verif/sim/out_*
rm -rf verif/sim/*_results/

# 清理 Git cache
git gc --aggressive --prune=now

# 清理 Docker（如果使用）
docker system prune -af
```

**预防措施**:
- 定期运行清理脚本
- 配置 artifact 保留期（GitLab: 7 天，GitHub: 7 天）

---

#### 3.1.4 License 超限

**症状**:
```
Error: Failed to checkout license for VCS
Error: Questa license not available
```

**根因**: 商业仿真器 license 并发数不足

**解决方案**:

```bash
# 检查 license 服务器状态
lmstat -a -c 27000@license-server

# 查看哪些 job 占用了 license
lmstat -a | grep <username>

# 等待其他 job 释放 license，或联系 CI 维护者增加 license
```

**预防措施**:
- 错峰运行测试（避免所有 job 同时启动）
- 使用 license queue 机制

---

### 3.2 测试失败问题

#### 3.2.1 RTL 和 ISS 不匹配

**症状**:
```
Test FAILED: rv64ui-p-add
Mismatch between RTL and ISS:
  PC: 0x80000020
  RTL: rd=x10, value=0x0000000000000005
  ISS: rd=x10, value=0x0000000000000006
```

**根因**: RTL 实现错误或 ISS (Spike) 行为不一致

**排查步骤**:

```bash
# 1. 本地复现
cd verif/sim
python3 cva6.py \
  --target cv64a6_imafdc_sv39 \
  --iss veri-testharness,spike \
  --test rv64ui-p-add \
  --iss_yaml cva6.yaml

# 2. 启用波形调试
python3 cva6.py \
  --target cv64a6_imafdc_sv39 \
  --iss veri-testharness \
  --test rv64ui-p-add \
  --trace

# 3. 查看波形
gtkwave trace_hart_0000.fst &

# 4. 查看详细日志
tail -200 veri-testharness_sim/rv64ui-p-add.log

# 5. 对比 Spike 日志
tail -200 spike_sim/rv64ui-p-add.log
```

**常见根因**:
- ALU 运算错误
- Load/Store 地址计算错误
- Branch 跳转逻辑错误
- CSR 读写错误

**解决方案**: 修复 RTL 代码，添加回归测试

---

#### 3.2.2 测试超时

**症状**:
```
Test TIMEOUT: rv64mi-p-breakpoint
Timeout after 300 seconds
```

**根因**: 测试卡死或运行时间过长

**排查步骤**:

```bash
# 1. 检查是否是死循环
# 查看 PC 是否一直在同一个地址
grep "PC:" logfile.log | tail -100

# 2. 检查是否是 WFI (Wait For Interrupt) 卡死
grep "wfi" logfile.log

# 3. 增加 timeout 重新运行
python3 cva6.py \
  --target cv64a6_imafdc_sv39 \
  --test rv64mi-p-breakpoint \
  --iss_timeout 600  # 增加到 10 分钟
```

**常见根因**:
- WFI 指令没有中断唤醒
- Exception handler 死循环
- Cache coherency 死锁
- 仿真器性能问题

**解决方案**:
- 修复 RTL 逻辑
- 优化测试（减少循环次数）
- 使用更快的仿真器（VCS/Questa 代替 Verilator）

---

#### 3.2.3 Assertion 失败

**症状**:
```
Assertion failed: (lsu_valid && lsu_ready) || !lsu_req
  at /path/to/cva6/core/load_store_unit.sv:123
```

**根因**: RTL 内部 assertion 检查失败（设计不变式被违反）

**排查步骤**:

```bash
# 1. 查看 assertion 上下文
grep -A 20 -B 20 "Assertion failed" logfile.log

# 2. 启用波形，查看信号值
python3 cva6.py --trace ...

# 3. 在波形中定位 assertion 失败时刻
# 搜索信号: lsu_valid, lsu_ready, lsu_req
```

**常见根因**:
- Handshake 协议违反（valid/ready 不一致）
- FIFO 满时仍然 push
- 状态机进入非法状态
- 时序问题（combinational loop）

**解决方案**: 修复 RTL 逻辑，确保 invariant 始终成立

---

#### 3.2.4 仿真器 Crash

**症状**:
```
Segmentation fault (core dumped)
verilator: internal error: ...
```

**根因**: 仿真器本身的 bug 或 RTL 代码触发了工具 bug

**排查步骤**:

```bash
# 1. 检查 Verilator 版本
verilator --version
# 确保是推荐版本 v5.008

# 2. 尝试使用其他仿真器
python3 cva6.py --iss vcs-testharness ...

# 3. 如果是 Verilator bug，简化测试用例
# 创建 minimal reproducible example

# 4. 报告 bug 到 Verilator 社区
# https://github.com/verilator/verilator/issues
```

**临时解决方案**:
- 使用其他仿真器（VCS, Questa）
- 降级或升级 Verilator 版本
- 修改 RTL 代码规避工具 bug

---

### 3.3 性能和超时问题

#### 3.3.1 编译超时

**症状**:
```
Timeout during Verilator compilation (>60 minutes)
```

**根因**: RTL 代码规模大，编译慢

**解决方案**:

```bash
# 1. 增加并行编译数
export NUM_JOBS=16
make veri-testharness NUM_JOBS=16

# 2. 使用增量编译（如果支持）
make veri-testharness INCREMENTAL=1

# 3. 使用预编译的 testbench（cache）
# GitHub Actions 已配置 cache

# 4. 使用更快的编译器
export CXX=clang++  # 代替 g++
```

---

#### 3.3.2 仿真超时

**症状**:
```
Test running for >2 hours
```

**根因**: Verilator 仿真速度慢（~100 KHz）

**解决方案**:

```bash
# 1. 使用更快的仿真器
# VCS: ~1-10 MHz
# Questa: ~500 KHz - 5 MHz
export DV_SIMULATORS=vcs-testharness

# 2. 减少测试指令数
# 编辑测试源码，减少循环次数

# 3. 禁用不必要的功能
# 禁用 trace, coverage, assertion
export TRACE=0
export COV=0
```

---

#### 3.3.3 报告生成超时

**症状**:
```
Coverage merge taking >30 minutes
```

**根因**: Coverage database 太大

**解决方案**:

```bash
# 1. 增量合并 coverage
vcover merge -out partial1.ucdb test1.ucdb test2.ucdb test3.ucdb
vcover merge -out partial2.ucdb test4.ucdb test5.ucdb test6.ucdb
vcover merge -out final.ucdb partial1.ucdb partial2.ucdb

# 2. 减少 coverage 详细程度
# 只收集 line + branch，不收集 toggle + FSM

# 3. 使用并行 merge
vcover merge -parallel ...
```

---

### 3.4 间歇性问题（Flaky Tests）

#### 症状

测试有时 PASS，有时 FAIL，无明显规律

#### 常见原因

| 原因 | 检测方法 | 解决方案 |
|------|----------|----------|
| **Timing 竞争** | 波形中看到 X 态 | 修复 RTL timing |
| **随机种子变化** | 不同 run 结果不同 | 固定 random seed |
| **资源竞争** | 高负载时失败 | 增加 runner 资源 |
| **网络不稳定** | submodule fetch 失败 | 添加 retry 机制 |

#### 通用排查步骤

```bash
# 1. 多次运行测试（10 次）
for i in {1..10}; do
  python3 cva6.py --test <test_name>
  echo "Run $i: $?"
done

# 2. 固定随机种子
python3 cva6.py --test <test_name> --seed 12345

# 3. 添加到 known_failures.yaml（临时措施）
- test: <test_name>
  status: flaky
  reason: "Random seed dependency"
```

---

## 四、高级故障排查

### 4.1 使用 Git Bisect 定位回归

当测试在某个 commit 后开始失败，使用 `git bisect` 找到引入 bug 的 commit：

```bash
# 1. 启动 bisect
git bisect start
git bisect bad HEAD  # 当前版本失败
git bisect good <last-known-good-commit>  # 上次成功的 commit

# 2. Git 会自动 checkout 中间的 commit，运行测试
cd verif/sim
bash ../regress/smoke-tests-cv64a6_imafdc_sv39.sh

# 3. 根据结果标记
git bisect good   # 如果测试通过
git bisect bad    # 如果测试失败

# 4. 重复步骤 2-3，直到找到第一个失败的 commit
# Git 会输出: <commit-hash> is the first bad commit

# 5. 结束 bisect
git bisect reset
```

---

### 4.2 Coverage 回归分析

当 coverage 下降时，找出未覆盖的新代码：

```bash
# 1. 生成当前 coverage 报告
vcover report -html -htmldir cov_current merged.ucdb

# 2. 对比上次的 coverage（需要保存历史 database）
vcover merge -out diff.ucdb -diff cov_current.ucdb cov_last.ucdb

# 3. 查看差异报告
vcover report -html -htmldir cov_diff diff.ucdb

# 4. 在 HTML 中查找 Coverage 下降的文件和行号
# 添加测试覆盖这些行
```

---

### 4.3 性能分析（Profile）

当 CI 运行时间过长时，分析瓶颈：

```bash
# 1. 使用 time 命令
time bash verif/regress/smoke-tests-cv64a6_imafdc_sv39.sh

# 2. 分析每个测试的时间
for test in rv64ui-p-* ; do
  time python3 cva6.py --test $test
done | tee timing.log

# 3. 排序找出最慢的测试
grep "real" timing.log | sort -nk2

# 4. 针对慢测试优化
#    - 减少指令数
#    - 使用更快的仿真器
#    - 并行运行
```

---

## 五、Escalation 流程

### 5.1 何时升级到 CI 维护者

如果遇到以下情况，请升级到 CI 维护者：

| 问题类型 | 升级条件 | 联系方式 |
|----------|----------|----------|
| **基础设施故障** | 所有 PR CI 失败 | Slack: #cva6-ci |
| **Runner 问题** | Runner 持续离线 >1 小时 | Email: ci-team@openhwgroup.org |
| **License 问题** | License 长期不可用 | 提交 GitLab issue |
| **工具 Bug** | Verilator/Spike 严重 bug | GitHub issue + @ci-maintainer |
| **性能问题** | CI 时间 >2x SLA | 周会讨论 |

---

### 5.2 Escalation 模板

**Issue 标题**: `[CI] <简短描述>`

**Issue 内容**:
```markdown
## 问题描述
[清晰描述问题]

## 复现步骤
1. 运行命令: `...`
2. 环境: `GitHub Actions / GitLab CI`
3. Runner: `ubuntu-latest / self-hosted`

## 错误日志
```
[粘贴最后 100 行日志]
```

## 已尝试的解决方案
- [ ] 检查了环境变量
- [ ] 清理了缓存
- [ ] 重新运行了 3 次

## 期望行为
[描述期望的正确行为]

## 优先级
- [ ] P0 - Critical (所有 CI 不可用)
- [x] P1 - High (影响 PR merge)
- [ ] P2 - Medium (单个测试失败)
- [ ] P3 - Low (性能优化)
```

---

## 六、故障排查工具箱

### 6.1 常用命令速查

```bash
# ===== 环境检查 =====
echo "RISCV: $RISCV"
echo "VERILATOR: $(which verilator)"
echo "SPIKE: $(which spike)"

# ===== 日志查看 =====
tail -100 verif/sim/logfile.log
grep -E "ERROR|FAIL" verif/sim/*.log

# ===== 波形调试 =====
gtkwave verif/sim/trace_hart_0000.fst &

# ===== 测试重运行 =====
python3 verif/sim/cva6.py --test <test_name>

# ===== 清理环境 =====
make -C verif/sim clean_all
make clean

# ===== Git 相关 =====
git submodule status
git submodule update --init --recursive
git bisect start

# ===== 性能分析 =====
time bash verif/regress/smoke-tests-*.sh
```

---

### 6.2 日志关键词搜索

| 关键词 | 含义 | 优先级 |
|--------|------|--------|
| `ERROR:` | 严重错误 | P1 |
| `FAIL:` | 测试失败 | P1 |
| `Traceback` | Python 异常 | P1 |
| `Timeout` | 超时 | P2 |
| `WARNING:` | 警告 | P3 |
| `Mismatch` | RTL/ISS 不匹配 | P1 |
| `Assertion` | Assertion 失败 | P1 |
| `Segmentation fault` | 程序 crash | P1 |

---

### 6.3 调试技巧

#### 1. 启用详细日志

```bash
# Python 脚本
export VERBOSE=1
python3 cva6.py --verbose ...

# Makefile
make V=1 ...

# Verilator
verilator --debug --trace ...
```

#### 2. 隔离问题

```bash
# 只运行失败的测试
python3 cva6.py --test rv64ui-p-add

# 只运行一个配置
export DV_TARGET=cv64a6_imafdc_sv39

# 只使用一个仿真器
export DV_SIMULATORS=veri-testharness
```

#### 3. 对比工作版本

```bash
# Checkout 上一个工作的 commit
git checkout <last-good-commit>

# 运行相同测试
bash verif/regress/smoke-tests-*.sh

# 对比差异
git diff HEAD <last-good-commit>
```

---

## 七、总结

### 7.1 快速参考卡

**CI 失败 → 5 步排查法**:
1. ❓ 哪个 job 失败？
2. 📋 查看日志最后 100 行
3. 🔍 分类（环境/测试/报告/超时）
4. 🛠️ 查找对应解决方案（§ 3）
5. 📞 无法解决 → 升级（§ 5）

**最常见 5 个问题**:
1. 环境变量未设置 → `source verif/sim/setup-env.sh`
2. Submodule 未初始化 → `git submodule update --init --recursive`
3. RTL/ISS 不匹配 → 修复 RTL bug
4. 测试超时 → 使用更快的仿真器
5. License 不可用 → 联系 CI 维护者

---

### 7.2 预防性措施

| 措施 | 效果 |
|------|------|
| **本地运行 smoke test** | 减少 90% PR CI 失败 |
| **使用 setup-local-env.sh** | 避免环境配置错误 |
| **提交前运行 lint** | 避免编译错误 |
| **小步提交** | 容易 bisect 定位问题 |
| **添加回归测试** | 避免重复问题 |

---

**相关文档**:
- [01_ci_for_beginners.md](./01_ci_for_beginners.md) - CI 基础概念
- [WEEK1_EXECUTION_GUIDE.md](./WEEK1_EXECUTION_GUIDE.md) - 环境配置故障排查
- [05_ci_contract.md](./05_ci_contract.md) - 了解 CI 保证范围
