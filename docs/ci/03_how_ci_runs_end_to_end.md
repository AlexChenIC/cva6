# CI 端到端流程详解

**文档版本**: v1.0
**创建日期**: 2026-01-18
**维护者**: OpenHW CI Team
**目标读者**: CI 维护者、希望深入理解 CI 机制的开发者

---

## 目录

1. [CI 触发机制](#一ci-触发机制)
2. [GitLab CI 完整流程](#二gitlab-ci-完整流程)
3. [GitHub Actions 完整流程](#三github-actions-完整流程)
4. [Artifacts 和数据流转](#四artifacts-和数据流转)
5. [报告生成和发布](#五报告生成和发布)
6. [Dashboard 更新机制](#六dashboard-更新机制)
7. [性能优化策略](#七性能优化策略)

---

## 一、CI 触发机制

### 1.1 GitLab CI 触发规则

CVA6 的 GitLab CI 使用 **动态触发机制**，基于 `CI_KIND` 变量决定运行哪些测试。

#### Workflow Rules (.gitlab-ci.yml:13-32)

```yaml
workflow:
  rules:
    # 1. Scheduled Pipeline (Nightly/Weekly)
    - if: $CI_PIPELINE_SOURCE == "schedule"
      variables:
        CI_KIND: verif

    # 2. Master Branch (Full Regression)
    - if: $CI_COMMIT_BRANCH == "master"
      variables:
        CI_KIND: regress

    # 3. Merge Request (Smoke Test)
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
      variables:
        CI_KIND: regress

    # 4. Feature Branch (Development)
    - if: $CI_COMMIT_BRANCH =~ /.*_PR_.*/
      variables:
        CI_KIND: dev

    # 5. Manual/Web Pipeline
    - if: $CI_PIPELINE_SOURCE == "web"
      when: always
```

#### CI_KIND 含义

| CI_KIND | 触发条件 | 运行测试范围 | 预计时间 |
|---------|----------|--------------|----------|
| `verif` | Scheduled (定时任务) | 完整验证（所有测试 + Coverage） | 6-24 小时 |
| `regress` | Master 分支或 MR | 回归测试（核心测试集） | 2-6 小时 |
| `dev` | Feature 分支 (xxx_PR_xxx) | 开发测试（快速验证） | 30 分钟-2 小时 |
| `none` | 其他分支 | 不运行测试 | 0 分钟 |

---

### 1.2 GitHub Actions 触发规则

GitHub Actions 的触发更简单，主要响应 **Pull Request** 事件。

#### Trigger Events (.github/workflows/ci.yml:3-9)

```yaml
on:
  pull_request:
    branches:
      - master
  push:
    branches:
      - master
  workflow_dispatch:  # 手动触发
```

#### 触发场景

| 事件 | 触发条件 | 运行内容 |
|------|----------|----------|
| `pull_request` | 向 master 提交 PR | Smoke test (Verilator + Spike) |
| `push` | 推送到 master | 完整测试（同 PR） |
| `workflow_dispatch` | 手动点击 "Run workflow" | 可配置（默认 smoke test） |

---

### 1.3 触发时机对比

| 维度 | GitLab CI | GitHub Actions |
|------|-----------|----------------|
| **自动触发** | MR, Push, Schedule | PR, Push |
| **手动触发** | Web UI, API | Workflow dispatch |
| **定时任务** | ✅ 支持（Cron） | ⏳ 需配置 schedule |
| **触发粒度** | 基于 CI_KIND 动态调整 | 固定测试集 |
| **灵活性** | 高（多种 CI_KIND） | 中（固定 workflow） |

---

## 二、GitLab CI 完整流程

### 2.1 Pipeline 架构（6 Stages）

GitLab CI 使用 **6 阶段流水线** 架构：

```
┌─────────────────────────────────────────────────────────────┐
│                      GitLab CI Pipeline                      │
├─────────────────────────────────────────────────────────────┤
│ Stage 1: setup          │ 环境准备、工具链安装              │
│ Stage 2: light tests    │ 快速测试（Smoke tests）           │
│ Stage 3: heavy tests    │ 完整回归测试                       │
│ Stage 4: backend tests  │ 综合工具测试（Synopsys, Yosys）   │
│ Stage 5: find failures  │ 日志分析、失败检测                 │
│ Stage 6: report         │ 报告生成、Coverage 合并           │
└─────────────────────────────────────────────────────────────┘
```

---

### 2.2 Stage 1: Setup（环境准备）

#### 关键 Jobs

**1. `tc-asm-tests-init`** - 初始化测试套件
```yaml
tc-asm-tests-init:
  stage: setup
  script:
    - git submodule update --init --recursive
    - bash verif/regress/install-riscv-tests.sh
    - bash verif/regress/install-riscv-arch-test.sh
```

**2. `tc-build-toolchain`** - 构建工具链（如果需要）
```yaml
tc-build-toolchain:
  stage: setup
  script:
    - source ci/install-toolchain.sh
    - bash verif/regress/install-verilator.sh
    - bash verif/regress/install-spike.sh
```

#### 产物 (Artifacts)

- RISC-V toolchain binaries
- Verilator binary
- Spike binary
- 测试套件源码（riscv-tests, riscv-arch-test）

---

### 2.3 Stage 2: Light Tests（快速测试）

#### 关键 Jobs

**1. `veri-testharness-smoke`** - Verilator Smoke Test
```yaml
veri-testharness-smoke:
  stage: light tests
  dependencies:
    - tc-asm-tests-init
  script:
    - export DV_SIMULATORS=veri-testharness,spike
    - export DV_TARGET=cv64a6_imafdc_sv39
    - bash verif/regress/smoke-tests-cv64a6_imafdc_sv39.sh
```

**2. `vcs-testharness-smoke`** - VCS Smoke Test
```yaml
vcs-testharness-smoke:
  stage: light tests
  only:
    variables:
      - $CI_KIND == "verif" || $CI_KIND == "regress"
  script:
    - export DV_SIMULATORS=vcs-testharness,spike
    - bash verif/regress/smoke-tests-cv64a6_imafdc_sv39.sh
```

#### 测试内容

- **riscv-tests**: rv64ui-p-add, rv64ui-v-add
- **riscv-arch-test**: rv64i_m-add-01
- **custom tests**: custom_test_template, hello_world.c
- **预计时间**: 10-20 分钟

---

### 2.4 Stage 3: Heavy Tests（完整回归）

#### 关键 Jobs

**1. `vcs-riscv-arch-test`** - RISC-V 架构测试
```yaml
vcs-riscv-arch-test:
  stage: heavy tests
  only:
    variables:
      - $CI_KIND == "verif"
  script:
    - export DV_SIMULATORS=vcs-testharness
    - bash verif/regress/dv-riscv-arch-test.sh
  artifacts:
    paths:
      - verif/sim/vcs_results/
```

**2. `vcs-riscv-tests-cv64a6`** - 完整 ISA 测试
```yaml
vcs-riscv-tests-cv64a6:
  stage: heavy tests
  script:
    - bash verif/regress/dv-riscv-tests.sh
```

#### 测试内容

- **riscv-arch-test**: 500+ 测试
- **riscv-tests**: 200+ 测试（rv64ui, rv64um, rv64ua, rv64uf, rv64ud, rv64si, rv64mi）
- **预计时间**: 2-4 小时

---

### 2.5 Stage 4: Backend Tests（综合测试）

#### 关键 Jobs

**1. `synth-gate-level`** - Gate-level 综合
```yaml
synth-gate-level:
  stage: backend tests
  only:
    variables:
      - $CI_KIND == "verif"
  script:
    - make -C pd/synth all
```

**2. `yosys-synthesis`** - Yosys 综合验证
```yaml
yosys-synthesis:
  stage: backend tests
  script:
    - python3 util/synthesize.py
```

#### 测试内容

- 综合到 FPGA 或 ASIC
- LEC (Logic Equivalence Checking)
- Timing 分析
- **预计时间**: 1-2 小时

---

### 2.6 Stage 5: Find Failures（失败检测）

#### 关键 Jobs

**1. `check-tests-passed`** - 检查测试通过率
```yaml
check-tests-passed:
  stage: find failures
  script:
    - python3 .gitlab-ci/scripts/check_tests.py
    - if [ $? -ne 0 ]; then exit 1; fi
```

#### 检查内容

- 解析所有 job 的日志
- 统计 PASS/FAIL 数量
- 生成失败测试列表
- 如果失败率 > 阈值，标记 pipeline 为 FAILED

---

### 2.7 Stage 6: Report（报告生成）

#### 关键 Jobs

**1. `report-coverage`** - Coverage 报告
```yaml
report-coverage:
  stage: report
  only:
    variables:
      - $CI_KIND == "verif"
  script:
    - python3 .gitlab-ci/scripts/report_coverage.py
    - vcover merge -out merged.ucdb vcs_results/**/*.ucdb
    - vcover report -html -htmldir cov_html merged.ucdb
  artifacts:
    paths:
      - cov_html/
```

**2. `report-tests`** - 测试结果报告
```yaml
report-tests:
  stage: report
  script:
    - python3 .gitlab-ci/scripts/report_builder.py
    - python3 .gitlab-ci/scripts/report_fail.py
  artifacts:
    reports:
      junit: report.xml
```

#### 产物

- **Coverage HTML 报告**: `cov_html/index.html`
- **JUnit XML 报告**: `report.xml`
- **失败测试清单**: `failed_tests.yaml`
- **Pipeline 总结**: `summary.json`

---

### 2.8 GitLab CI 时间线（典型 Verif Run）

```
00:00:00  ┌─ Stage 1: setup (10 min)
00:10:00  ├─ Stage 2: light tests (20 min, 并行)
00:30:00  ├─ Stage 3: heavy tests (4 hr, 并行)
04:30:00  ├─ Stage 4: backend tests (1.5 hr, 并行)
06:00:00  ├─ Stage 5: find failures (5 min)
06:05:00  └─ Stage 6: report (10 min)
06:15:00  ✓ Pipeline 完成
```

---

## 三、GitHub Actions 完整流程

### 3.1 Workflow 架构（3 Jobs）

GitHub Actions 使用 **简化的 3-job 架构**：

```
┌─────────────────────────────────────────────────────────────┐
│                   GitHub Actions Workflow                    │
├─────────────────────────────────────────────────────────────┤
│ Job 1: build-riscv-tests     │ 构建工具链和测试套件        │
│ Job 2: execute-riscv64-tests │ 运行 RV64 测试（并行 6 个）│
│ Job 3: execute-riscv32-tests │ 运行 RV32 测试（并行 2 个）│
└─────────────────────────────────────────────────────────────┘
```

---

### 3.2 Job 1: build-riscv-tests（构建）

#### 执行步骤

```yaml
build-riscv-tests:
  runs-on: ubuntu-latest
  steps:
    # 1. Checkout 代码
    - uses: actions/checkout@v4
      with:
        submodules: recursive

    # 2. Cache 工具链（Level 1）
    - uses: actions/cache@v3
      with:
        path: tools/riscv-toolchain/
        key: ${{ runner.os }}-toolchain-${{ hashFiles('ci/install-toolchain.sh') }}

    # 3. Cache Verilator（Level 2）
    - uses: actions/cache@v3
      with:
        path: tools/verilator/
        key: ${{ runner.os }}-verilator-v5.008

    # 4. Cache Spike（Level 3）
    - uses: actions/cache@v3
      with:
        path: tools/spike/
        key: ${{ runner.os }}-spike-${{ hashFiles('verif/regress/install-spike.sh') }}

    # 5. 运行安装脚本
    - name: Install tools
      run: bash ci/setup.sh

    # 6. 上传 artifacts
    - uses: actions/upload-artifact@v4
      with:
        name: build-artifacts
        path: |
          tools/
          verif/tests/
```

#### Cache 策略（3 级缓存）

| 级别 | 内容 | Cache Key | 命中率 | 节省时间 |
|------|------|-----------|--------|----------|
| L1 | RISC-V toolchain | install-toolchain.sh hash | 95% | ~30 min |
| L2 | Verilator v5.008 | 固定版本 | 98% | ~15 min |
| L3 | Spike ISS | install-spike.sh hash | 90% | ~5 min |

**首次运行**: ~50 分钟（构建所有工具）
**Cache 命中**: ~5 分钟（仅下载和解压）

---

### 3.3 Job 2: execute-riscv64-tests（RV64 测试）

#### Matrix 策略（6 并行 jobs）

```yaml
execute-riscv64-tests:
  needs: build-riscv-tests
  runs-on: ubuntu-latest
  strategy:
    matrix:
      testcase:
        - cv64a6_imafdc_tests
        - dv-riscv-arch-test
      config:
        - cv64a6_imafdc_sv39_hpdcache
        - cv64a6_imafdc_sv39_hpdcache_wb
        - cv64a6_imafdc_sv39_wb
  steps:
    - name: Download artifacts
      uses: actions/download-artifact@v4

    - name: Run tests
      run: |
        export DV_SIMULATORS=veri-testharness,spike
        export DV_TARGET=${{ matrix.config }}
        bash verif/regress/${{ matrix.testcase }}.sh
```

#### 测试矩阵

| testcase | config | 测试数量 | 预计时间 |
|----------|--------|----------|----------|
| cv64a6_imafdc_tests | cv64a6_imafdc_sv39_hpdcache | ~50 | 10 min |
| cv64a6_imafdc_tests | cv64a6_imafdc_sv39_hpdcache_wb | ~50 | 10 min |
| cv64a6_imafdc_tests | cv64a6_imafdc_sv39_wb | ~50 | 10 min |
| dv-riscv-arch-test | cv64a6_imafdc_sv39_hpdcache | ~200 | 15 min |
| dv-riscv-arch-test | cv64a6_imafdc_sv39_hpdcache_wb | ~200 | 15 min |
| dv-riscv-arch-test | cv64a6_imafdc_sv39_wb | ~200 | 15 min |

**总测试数**: ~800 测试
**并行运行时间**: ~15 分钟（6 个 runner 并行）

---

### 3.4 Job 3: execute-riscv32-tests（RV32 测试）

#### Matrix 策略（2 并行 jobs）

```yaml
execute-riscv32-tests:
  needs: build-riscv-tests
  runs-on: ubuntu-latest
  strategy:
    matrix:
      config:
        - cv32a65x
        - cv32a6_imac_sv0
  steps:
    - name: Run tests
      run: |
        export DV_TARGET=${{ matrix.config }}
        bash verif/regress/cv32-riscv-tests.sh
```

**总测试数**: ~100 测试
**并行运行时间**: ~10 分钟

---

### 3.5 GitHub Actions 时间线（典型 PR）

```
00:00:00  ┌─ Job 1: build-riscv-tests (5 min, cache 命中)
00:05:00  ├─ Job 2: execute-riscv64-tests (15 min, 6 并行)
          ├─ Job 3: execute-riscv32-tests (10 min, 2 并行)
00:20:00  └─ Workflow 完成
```

**总时间**: 20-25 分钟（cache 命中）
**首次运行**: 50-60 分钟（需构建工具）

---

## 四、Artifacts 和数据流转

### 4.1 GitLab CI Artifacts

#### 数据流向

```
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│ Stage 1-4   │─────>│ Stage 5     │─────>│ Stage 6     │
│ 测试日志     │ logs │ 失败检测     │ list │ 报告生成     │
│ Coverage DB │─────>│             │─────>│ HTML Report │
└─────────────┘      └─────────────┘      └─────────────┘
```

#### Artifacts 类型

| 类型 | 文件 | 保留时间 | 用途 |
|------|------|----------|------|
| **测试日志** | `verif/sim/*.log` | 7 天 | 故障排查 |
| **Coverage DB** | `*.ucdb` | 30 天 | 趋势分析 |
| **JUnit XML** | `report.xml` | 永久 | GitLab UI 显示 |
| **HTML 报告** | `cov_html/` | 30 天 | 浏览器查看 |

---

### 4.2 GitHub Actions Artifacts

#### 数据流向

```
┌─────────────────┐      ┌─────────────────┐
│ build-riscv-    │─────>│ execute-riscv*- │
│ tests           │ tools│ tests           │
│ (构建工具)       │─────>│ (运行测试)       │
└─────────────────┘      └─────────────────┘
         │                        │
         └────────────────────────┘
                    │
                    v
          ┌─────────────────┐
          │ Upload artifacts│
          │ (测试结果)       │
          └─────────────────┘
```

#### Artifacts 类型

| 名称 | 内容 | 大小 | 保留时间 |
|------|------|------|----------|
| `build-artifacts` | tools/, verif/tests/ | ~2 GB | 1 天 |
| `test-results-rv64` | verif/sim/out_* | ~50 MB | 7 天 |
| `test-results-rv32` | verif/sim/out_* | ~20 MB | 7 天 |

---

## 五、报告生成和发布

### 5.1 GitLab 报告生成流程

#### 1. 日志收集

```python
# .gitlab-ci/scripts/report_builder.py

def collect_logs():
    """收集所有 job 的日志"""
    logs = []
    for job in jobs:
        log_file = f"verif/sim/{job}/logfile.log"
        logs.append(parse_log(log_file))
    return logs
```

#### 2. 测试结果解析

```python
def parse_log(log_file):
    """解析测试日志"""
    results = {
        'passed': [],
        'failed': [],
        'timeout': []
    }

    with open(log_file) as f:
        for line in f:
            if "Test passed" in line:
                results['passed'].append(extract_test_name(line))
            elif "Test FAILED" in line:
                results['failed'].append(extract_test_name(line))

    return results
```

#### 3. Coverage 合并

```bash
# 合并所有 coverage database
vcover merge -out merged.ucdb \
    vcs_results/job1/coverage.ucdb \
    vcs_results/job2/coverage.ucdb \
    vcs_results/job3/coverage.ucdb

# 生成 HTML 报告
vcover report -html -htmldir cov_html merged.ucdb
```

#### 4. JUnit XML 生成

```python
# .gitlab-ci/scripts/report_builder.py

def generate_junit_xml(results):
    """生成 JUnit 格式 XML"""
    xml = ElementTree.Element("testsuites")

    for suite_name, tests in results.items():
        testsuite = ElementTree.SubElement(xml, "testsuite",
                                           name=suite_name,
                                           tests=str(len(tests)))

        for test in tests:
            testcase = ElementTree.SubElement(testsuite, "testcase",
                                             name=test.name,
                                             time=str(test.duration))
            if test.status == "FAILED":
                failure = ElementTree.SubElement(testcase, "failure",
                                                message=test.error_msg)

    tree = ElementTree.ElementTree(xml)
    tree.write("report.xml")
```

---

### 5.2 GitHub Actions 报告生成

#### 1. Test Summary（PR 评论）

```yaml
- name: Post test summary
  if: always()
  uses: actions/github-script@v6
  with:
    script: |
      const fs = require('fs');
      const results = JSON.parse(fs.readFileSync('test_results.json'));

      const summary = `
      ## 🧪 CVA6 CI Test Results

      **Status**: ${results.status}
      **Tests Run**: ${results.total}
      **Passed**: ✅ ${results.passed}
      **Failed**: ❌ ${results.failed}

      ### Details
      - **RV64 Tests**: ${results.rv64.passed}/${results.rv64.total}
      - **RV32 Tests**: ${results.rv32.passed}/${results.rv32.total}

      [View full report](${results.report_url})
      `;

      github.rest.issues.createComment({
        issue_number: context.issue.number,
        owner: context.repo.owner,
        repo: context.repo.repo,
        body: summary
      });
```

#### 2. 生成的 PR 评论示例

```markdown
## 🧪 CVA6 CI Test Results

**Status**: ✅ PASSED
**Tests Run**: 850
**Passed**: ✅ 847
**Failed**: ❌ 3

### Details
- **RV64 Tests**: 747/750
- **RV32 Tests**: 100/100

### Failed Tests
1. `rv64ua-p-amoadd_w` - Timeout
2. `rv64mi-p-csr` - Assertion failure
3. `rv64si-p-wfi` - Mismatch with ISS

[View full logs](https://github.com/openhwgroup/cva6/actions/runs/12345)
```

---

## 六、Dashboard 更新机制

### 6.1 GitLab Dashboard

#### 更新流程

```
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│ Pipeline    │─────>│ GitLab API  │─────>│ Dashboard   │
│ 完成         │ POST │ (Webhook)   │ JSON │ (更新)      │
└─────────────┘      └─────────────┘      └─────────────┘
```

#### Dashboard 数据结构

```json
{
  "pipeline_id": 12345,
  "commit_sha": "abc123",
  "status": "success",
  "duration": 22500,  // 秒
  "tests": {
    "total": 1200,
    "passed": 1195,
    "failed": 5,
    "timeout": 0
  },
  "coverage": {
    "line": 92.5,
    "branch": 88.3,
    "fsm": 95.1
  },
  "timestamp": "2026-01-18T10:00:00Z"
}
```

---

### 6.2 Grafana Dashboard（示例）

#### 可视化指标

1. **测试通过率趋势图**
   - X 轴: 日期
   - Y 轴: 通过率 (%)
   - 数据源: GitLab API

2. **Coverage 趋势图**
   - Line coverage
   - Branch coverage
   - FSM coverage

3. **Pipeline 运行时间**
   - 平均运行时间
   - P95 运行时间
   - 运行时间分布

4. **失败测试 Top 10**
   - 最常失败的测试
   - 失败频率
   - 首次失败日期

---

## 七、性能优化策略

### 7.1 Cache 优化

#### GitLab CI Cache

```yaml
cache:
  key: ${CI_COMMIT_REF_SLUG}
  paths:
    - tools/riscv-toolchain/
    - tools/verilator/
    - tools/spike/
  policy: pull-push
```

**优化效果**:
- 首次运行: ~60 分钟
- Cache 命中: ~10 分钟
- 时间节省: **83%**

---

### 7.2 并行化策略

#### GitLab CI 并行化

```yaml
# 使用 parallel 关键字
vcs-tests-parallel:
  parallel:
    matrix:
      - CONFIG: [cv64a6, cv32a65x, cv32a6]
        ISA: [rv64ui, rv64um, rv64ua]
```

**优化效果**:
- 串行运行: 3 × 3 × 30 min = 4.5 小时
- 并行运行: max(30 min) = 30 分钟
- 时间节省: **89%**

---

### 7.3 增量测试

#### Smart Test Selection

```python
def select_tests(changed_files):
    """根据变更的文件选择测试"""
    tests = []

    if any('core/frontend' in f for f in changed_files):
        tests.extend(frontend_tests)
    if any('core/cache' in f for f in changed_files):
        tests.extend(cache_tests)
    if any('core/fpu' in f for f in changed_files):
        tests.extend(fpu_tests)

    # 总是运行 smoke tests
    tests.extend(smoke_tests)

    return list(set(tests))
```

**优化效果**:
- 完整测试: 1200 测试，4 小时
- 增量测试: ~300 测试，1 小时
- 时间节省: **75%**

---

## 八、故障诊断流程

### 8.1 CI 失败诊断决策树

```
CI 失败
  │
  ├─ Stage 1-2 失败？
  │   ├─ 工具链安装失败 → 检查网络、磁盘空间
  │   └─ Smoke test 失败 → 检查代码变更
  │
  ├─ Stage 3 失败？
  │   ├─ 大量测试失败 (>50%) → RTL 重大错误
  │   └─ 少量测试失败 (<10%) → 特定功能回归
  │
  ├─ Stage 4 失败？
  │   └─ 综合失败 → Timing 问题、Lint 错误
  │
  └─ Stage 5-6 失败？
      └─ 报告生成失败 → 脚本错误、权限问题
```

---

### 8.2 常见 CI 问题和解决方案

| 问题 | 症状 | 解决方案 |
|------|------|----------|
| **Cache 失效** | 每次都重新构建工具 | 检查 cache key 配置 |
| **Runner 离线** | Pipeline 卡在 pending | 重启 GitLab Runner |
| **磁盘空间不足** | Artifacts 上传失败 | 清理旧 artifacts |
| **License 超限** | VCS/Questa 失败 | 检查 license 服务器 |
| **网络超时** | Git submodule 失败 | 增加 timeout，检查代理 |

---

## 九、最佳实践

### 9.1 CI 配置最佳实践

1. **使用 only/except 控制 job 运行**
   ```yaml
   expensive-test:
     only:
       variables:
         - $CI_KIND == "verif"  # 仅在 weekly run 运行
   ```

2. **设置合理的 timeout**
   ```yaml
   long-running-test:
     timeout: 2h  # 避免无限卡住
   ```

3. **使用 retry 处理间歇性失败**
   ```yaml
   flaky-test:
     retry: 2  # 失败后重试 2 次
   ```

4. **分离 build 和 test**
   - 构建工具 → artifact
   - 测试 job 下载 artifact
   - 避免重复构建

---

### 9.2 性能优化最佳实践

1. **合理使用 cache**
   - 固定工具版本 → cache key 稳定
   - 大文件（toolchain）使用 cache
   - 频繁变化的文件不要 cache

2. **最大化并行度**
   - 使用 matrix 策略
   - 独立测试并行运行
   - 注意 runner 数量限制

3. **优化 Docker 镜像**
   - 预装常用工具
   - 使用多阶段构建
   - 最小化镜像大小

---

## 十、总结

### 10.1 GitLab CI vs GitHub Actions

| 维度 | GitLab CI | GitHub Actions |
|------|-----------|----------------|
| **复杂度** | 高（6 stages, 40+ jobs） | 低（3 jobs） |
| **测试覆盖** | 完整（1200+ 测试 + Coverage） | 基础（~850 测试） |
| **运行时间** | 6-24 小时（verif） | 20-25 分钟（smoke） |
| **触发粒度** | 灵活（CI_KIND 动态） | 固定（PR/Push） |
| **适用场景** | Nightly/Weekly regression | PR-level smoke test |

---

### 10.2 关键指标

| 指标 | GitLab CI (verif) | GitHub Actions (PR) |
|------|-------------------|---------------------|
| **Pipeline 时间** | 6-8 小时 | 20-25 分钟 |
| **测试数量** | 1200+ | ~850 |
| **Coverage 收集** | ✅ | ❌ |
| **成本** | 高（self-hosted + licenses） | 低（GitHub-hosted） |

---

## 附录：关键脚本索引

| 脚本 | 路径 | 用途 |
|------|------|------|
| Smoke test | `verif/regress/smoke-tests-*.sh` | 快速验证 |
| RISC-V tests | `verif/regress/dv-riscv-tests.sh` | ISA 测试 |
| Arch test | `verif/regress/dv-riscv-arch-test.sh` | 架构合规测试 |
| 报告生成 | `.gitlab-ci/scripts/report_builder.py` | 测试报告 |
| Coverage 报告 | `.gitlab-ci/scripts/report_coverage.py` | Coverage HTML |
| 失败检测 | `.gitlab-ci/scripts/check_tests.py` | 失败测试统计 |

---

**下一步阅读**: [05_ci_contract.md](./05_ci_contract.md) - 了解 CI 保证什么、不保证什么
