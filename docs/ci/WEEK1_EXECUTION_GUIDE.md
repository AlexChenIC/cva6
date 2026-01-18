# Week 1 执行指南

**目标**: 搭建本地 CVA6 CI 环境并验证基础功能

**预计时间**: 2-3 小时（不含工具编译时间）

**最终交付**: 本地成功运行 smoke test 并生成 PASS/FAIL 报告

---

## 一、前置条件检查

### 1.1 硬件要求

- **CPU 核心数**: ≥4 核（推荐 8 核以上）
- **内存**: ≥16GB（推荐 32GB）
- **磁盘空间**: ≥30GB 可用空间
- **操作系统**: Linux（Ubuntu 20.04/22.04 或 RHEL 8+）

### 1.2 必需软件

运行以下命令检查：

```bash
# 检查 Python 版本（需要 3.6+）
python3 --version

# 检查 Git
git --version

# 检查编译工具
gcc --version
make --version
```

如果缺少工具，请安装：

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y git python3 python3-pip build-essential \
    autoconf automake libtool curl make g++ unzip

# RHEL/CentOS
sudo yum install -y git python3 python3-pip gcc gcc-c++ make \
    autoconf automake libtool
```

---

## 二、环境配置（Step-by-Step）

### 2.1 进入 CVA6 根目录

```bash
cd /home/junchao/1_OpenHW_Work/github/cva6/ci_flow/1_ci_learning/cva6

# 验证目录正确
ls -la | grep -E "Makefile|verif|core"
```

**预期输出**: 应该看到 Makefile, verif/, core/ 等目录。

---

### 2.2 配置 RISC-V 工具链

**您已有工具链**: `/home/junchao/2_System_Setup/riscv_toolchain`

**设置环境变量**:

```bash
export RISCV=/home/junchao/2_System_Setup/riscv_toolchain
export CV_SW_PREFIX=riscv-none-elf-
export NUM_JOBS=10  # 根据您的 CPU 核心数调整
```

**验证工具链**:

```bash
$RISCV/bin/${CV_SW_PREFIX}gcc --version
```

**预期输出**: `riscv-none-elf-gcc (GCC) 13.1.0`

---

### 2.3 配置 Verilator

**您已有 Verilator**: `/home/junchao/2_System_Setup/verilator`

```bash
export VERILATOR_INSTALL_DIR=/home/junchao/2_System_Setup/verilator
export PATH=$VERILATOR_INSTALL_DIR/bin:$PATH
```

**验证 Verilator**:

```bash
verilator --version
```

**预期输出**: `Verilator 5.008` ✅ (推荐版本)

---

### 2.4 配置 Spike ISS

**您已有 Spike**: `/home/junchao/2_System_Setup/spike`

```bash
export SPIKE_INSTALL_DIR=/home/junchao/2_System_Setup/spike
export SPIKE_PATH=$SPIKE_INSTALL_DIR/bin
export PATH=$SPIKE_PATH:$PATH
```

**⚠️ 关键**: 还需要设置 SPIKE_SRC_DIR（cva6.py 需要）

```bash
# 设置为 CVA6 submodule 中的 Spike 源码路径
export SPIKE_SRC_DIR=$PWD/verif/core-v-verif/vendor/riscv/riscv-isa-sim
```

**验证 Spike**:

```bash
spike --version
ls -d $SPIKE_SRC_DIR
```

**预期输出**:
```
1.1.1-dev 60e57248
/home/junchao/.../cva6/verif/core-v-verif/vendor/riscv/riscv-isa-sim
```

---

### 2.5 加载 CVA6 环境配置

```bash
source verif/sim/setup-env.sh
```

**验证环境**:

```bash
echo "ROOT_PROJECT: $ROOT_PROJECT"
echo "RISCV: $RISCV"
echo "SPIKE_SRC_DIR: $SPIKE_SRC_DIR"
echo "SPIKE_INSTALL_DIR: $SPIKE_INSTALL_DIR"
```

**预期输出**: 所有变量都应该有值，且路径存在。

---

## 三、运行 Smoke Test

### 3.1 第一次运行（安装测试套件）

smoke test 脚本会自动安装以下测试套件：
- riscv-compliance (riscv-arch-test)
- riscv-tests
- riscv-arch-test

**首次运行命令**:

```bash
# 设置仿真器和目标配置
export DV_SIMULATORS=veri-testharness,spike
export DV_TARGET=cv64a6_imafdc_sv39

# 运行 smoke test（6 个测试）
bash verif/regress/smoke-tests-cv64a6_imafdc_sv39.sh 2>&1 | tee smoke_test_$(date +%Y%m%d_%H%M%S).log
```

**预计时间**:
- 首次运行: ~15-20 分钟（包含测试套件下载和编译）
- 后续运行: ~5-10 分钟

---

### 3.2 Smoke Test 包含的测试

该脚本运行以下 6 个测试：

1. **rv32i-I-ADD-01** (riscv-compliance)
   - 验证 RV32I 基础整数指令

2. **rv64ui-v-add** (riscv-tests, virtual mode)
   - 验证 RV64 用户态整数加法（虚拟内存）

3. **rv64ui-p-add** (riscv-tests, physical mode)
   - 验证 RV64 用户态整数加法（物理地址）

4. **rv64i_m-add-01** (riscv-arch-test)
   - RISC-V 架构测试套件

5. **custom_test_template** (custom test)
   - CVA6 自定义测试模板

6. **hello_world.c** (C 测试)
   - C 语言编译和执行验证

---

### 3.3 常见错误和解决方案

#### 错误 1: SPIKE_SRC_DIR 未设置

**错误信息**:
```
FileNotFoundError: [Errno 2] No such file or directory:
'...verif/core-v-verif/vendor/riscv/riscv-isa-sim'
```

**解决方案**:
```bash
export SPIKE_SRC_DIR=$PWD/verif/core-v-verif/vendor/riscv/riscv-isa-sim
```

---

#### 错误 2: Git submodule 未初始化

**错误信息**:
```
ls: cannot access 'verif/core-v-verif/': No such file or directory
```

**解决方案**:
```bash
git submodule update --init --recursive
```

---

#### 错误 3: RISCV 环境变量未设置

**错误信息**:
```
Error: RISCV variable undefined
```

**解决方案**:
```bash
export RISCV=/home/junchao/2_System_Setup/riscv_toolchain
source verif/sim/setup-env.sh
```

---

#### 错误 4: Python 模块缺失

**错误信息**:
```
ModuleNotFoundError: No module named 'yaml'
```

**解决方案**:
```bash
pip3 install pyyaml
```

---

#### 错误 5: Verilator 编译失败（内存不足）

**错误信息**:
```
c++: fatal error: Killed signal terminated program cc1plus
```

**解决方案**:
```bash
# 减少并行编译数
export NUM_JOBS=2
```

---

## 四、验证测试结果

### 4.1 检查测试日志

```bash
# 查看最新的 smoke test 日志
tail -100 smoke_test_*.log

# 查看 verif/sim 目录下的日志
cd verif/sim
ls -lht *.log | head -5
tail -50 logfile.log
```

---

### 4.2 判断测试是否通过

**成功标志**:
```
Test passed - match with ISS
```

**失败标志**:
```
Test FAILED
ERROR: ...
Mismatch between RTL and ISS
```

---

### 4.3 生成测试报告

运行以下命令生成简单的 PASS/FAIL 清单：

```bash
cd verif/sim
grep -r "Test passed" . | wc -l  # 统计通过的测试数
grep -r "Test FAILED" . | wc -l  # 统计失败的测试数
```

**手动创建报告**:

```bash
cat > smoke_test_report.txt << 'EOF'
# CVA6 Smoke Test Report
# Date: $(date +%Y-%m-%d)

## Test Summary
- Total Tests: 6
- Passed: [填写]
- Failed: [填写]

## Test Details
1. rv32i-I-ADD-01:        [PASS/FAIL]
2. rv64ui-v-add:          [PASS/FAIL]
3. rv64ui-p-add:          [PASS/FAIL]
4. rv64i_m-add-01:        [PASS/FAIL]
5. custom_test_template:  [PASS/FAIL]
6. hello_world.c:         [PASS/FAIL]

## Environment
- RISCV Toolchain: riscv-none-elf-gcc 13.1.0
- Verilator: 5.008
- Spike: 1.1.1-dev
- Target: cv64a6_imafdc_sv39
- Simulators: veri-testharness, spike

## Logs
- Smoke test log: smoke_test_YYYYMMDD_HHMMSS.log
- Detailed logs: verif/sim/logfile.log
EOF
```

---

## 五、Week 1 完成 Checklist

完成以下 checklist 即可认为 Week 1 任务完成：

### 5.1 环境配置

- [ ] RISC-V 工具链验证通过（`riscv-none-elf-gcc --version`）
- [ ] Verilator 安装并验证（`verilator --version` 输出 v5.008）
- [ ] Spike 安装并验证（`spike --version`）
- [ ] 所有环境变量正确设置（RISCV, SPIKE_SRC_DIR, etc.）
- [ ] Git submodules 已初始化（`git submodule status` 无 `-` 前缀）

### 5.2 测试套件

- [ ] riscv-compliance 已下载（`ls verif/tests/riscv-compliance`）
- [ ] riscv-tests 已下载（`ls verif/tests/riscv-tests`）
- [ ] riscv-arch-test 已下载（`ls verif/tests/riscv-arch-test`）

### 5.3 Smoke Test

- [ ] Smoke test 脚本成功运行（无 Python traceback 错误）
- [ ] 至少 5/6 个测试通过（允许 1 个测试失败）
- [ ] 生成了测试日志文件
- [ ] 创建了测试报告（手动或脚本生成）

### 5.4 文档

- [ ] 阅读了 `01_ci_for_beginners.md`
- [ ] 浏览了 `02_current_cva6_ci_inventory.md`
- [ ] 理解了 smoke test 的 6 个测试内容
- [ ] 记录了遇到的问题和解决方案

---

## 六、故障排查命令速查

```bash
# 环境检查
echo "RISCV: $RISCV"
echo "SPIKE_SRC_DIR: $SPIKE_SRC_DIR"
echo "VERILATOR_INSTALL_DIR: $VERILATOR_INSTALL_DIR"

# 工具验证
$RISCV/bin/riscv-none-elf-gcc --version
verilator --version
spike --version

# 查看测试日志
tail -100 verif/sim/logfile.log

# 清理环境（如果需要重新运行）
cd verif/sim
make clean_all
cd ../..
make clean

# 查看子模块状态
git submodule status

# 重新初始化子模块
git submodule update --init --recursive
```

---

## 七、下一步（Week 2 准备）

Week 1 完成后，准备以下内容为 Week 2 做准备：

1. **整理 Week 1 测试报告**
   - 记录测试通过/失败情况
   - 记录遇到的问题和解决方案
   - 记录环境配置过程中的经验

2. **准备 Self-hosted Runner**
   - 确认 runner 机器的配置
   - 确认网络连接和 GitHub 访问权限
   - 了解 GitHub Actions runner 安装流程

3. **复习 GitHub Actions**
   - 阅读 `.github/workflows/ci.yml`
   - 理解 cache 策略
   - 理解 matrix 策略

---

## 八、快速参考卡

### 完整环境配置（复制粘贴）

```bash
# 进入 CVA6 根目录
cd /home/junchao/1_OpenHW_Work/github/cva6/ci_flow/1_ci_learning/cva6

# 设置环境变量
export RISCV=/home/junchao/2_System_Setup/riscv_toolchain
export CV_SW_PREFIX=riscv-none-elf-
export NUM_JOBS=10
export VERILATOR_INSTALL_DIR=/home/junchao/2_System_Setup/verilator
export SPIKE_INSTALL_DIR=/home/junchao/2_System_Setup/spike
export SPIKE_PATH=$SPIKE_INSTALL_DIR/bin
export SPIKE_SRC_DIR=$PWD/verif/core-v-verif/vendor/riscv/riscv-isa-sim
export PATH=$VERILATOR_INSTALL_DIR/bin:$RISCV/bin:$SPIKE_PATH:$PATH

# 加载 CVA6 环境
source verif/sim/setup-env.sh

# 验证环境
echo "✓ RISCV: $RISCV"
echo "✓ SPIKE_SRC_DIR: $SPIKE_SRC_DIR"
echo "✓ Verilator: $(verilator --version 2>&1 | head -1)"
echo "✓ Spike: $(spike --version 2>&1 | head -1)"
echo "✓ GCC: $($RISCV/bin/${CV_SW_PREFIX}gcc --version | head -1)"

# 运行 smoke test
export DV_SIMULATORS=veri-testharness,spike
export DV_TARGET=cv64a6_imafdc_sv39
bash verif/regress/smoke-tests-cv64a6_imafdc_sv39.sh 2>&1 | tee smoke_test_$(date +%Y%m%d_%H%M%S).log
```

### 保存环境配置（下次直接加载）

```bash
# 将上述配置保存到文件
cat > ~/.cva6_env << 'EOF'
export RISCV=/home/junchao/2_System_Setup/riscv_toolchain
export CV_SW_PREFIX=riscv-none-elf-
export NUM_JOBS=10
export VERILATOR_INSTALL_DIR=/home/junchao/2_System_Setup/verilator
export SPIKE_INSTALL_DIR=/home/junchao/2_System_Setup/spike
export SPIKE_PATH=$SPIKE_INSTALL_DIR/bin
export PATH=$VERILATOR_INSTALL_DIR/bin:$RISCV/bin:$SPIKE_PATH:$PATH

# 进入 CVA6 目录后设置
if [ -f "verif/sim/setup-env.sh" ]; then
    export SPIKE_SRC_DIR=$PWD/verif/core-v-verif/vendor/riscv/riscv-isa-sim
    source verif/sim/setup-env.sh
fi
EOF

# 下次使用时
source ~/.cva6_env
```

---

## 九、获取帮助

### 文档资源

- **CI 入门**: `docs/ci/01_ci_for_beginners.md`
- **当前 CI 清单**: `docs/ci/02_current_cva6_ci_inventory.md`
- **文档导航**: `docs/ci/00_README.md`

### 社区资源

- **GitHub Issues**: https://github.com/openhwgroup/cva6/issues
- **OpenHW Slack**: cva6 频道

### 常见问题解决流程

1. 查看本文档的「常见错误和解决方案」（§3.3）
2. 查看 `01_ci_for_beginners.md` 的故障排查章节
3. 检查测试日志文件
4. 在 GitHub 搜索类似问题
5. 提交新的 issue（附上错误日志）

---

**祝您 Week 1 顺利完成！** 🎉
