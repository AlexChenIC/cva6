# Runner 和 License 检查清单

**文档版本**: v1.0
**创建日期**: 2026-01-18
**维护者**: OpenHW CI Team
**目标读者**: CI 维护者、系统管理员

---

## 文档目的

本文档提供 **Self-hosted Runner 和 License 管理的完整清单**，包括：
- 🖥️ Runner 环境配置要求
- 🔑 License 配置和验证
- 📌 工具版本锁定策略
- 🔧 故障排查命令集

---

## 目录

1. [Self-hosted Runner 要求](#一self-hosted-runner-要求)
2. [License 配置管理](#二license-配置管理)
3. [工具版本管理](#三工具版本管理)
4. [Runner 监控和维护](#四runner-监控和维护)
5. [故障排查清单](#五故障排查清单)
6. [安全和权限管理](#六安全和权限管理)

---

## 一、Self-hosted Runner 要求

### 1.1 硬件要求

#### 最低配置

| 组件 | 最低要求 | 推荐配置 | 备注 |
|------|----------|----------|------|
| **CPU** | 8 核 | 16-32 核 | 支持 AVX2 指令集 |
| **内存** | 32 GB | 64-128 GB | Verilator 编译需要大内存 |
| **磁盘** | 500 GB SSD | 1-2 TB NVMe SSD | 需要高 IOPS |
| **网络** | 100 Mbps | 1 Gbps | 下载 artifacts 和 cache |

#### 磁盘空间规划

```
/                       100 GB  (系统和应用)
/home/<runner>          200 GB  (Runner 工作目录)
/tmp                    200 GB  (编译临时文件)
/var/lib/docker         200 GB  (Docker images，如果使用)
/data/ci                500 GB  (Artifacts, cache, logs)
```

---

### 1.2 操作系统要求

#### 支持的操作系统

| OS | 版本 | 状态 | 备注 |
|------|------|------|------|
| **Ubuntu** | 20.04 LTS, 22.04 LTS | ✅ 推荐 | 最佳兼容性 |
| **RHEL** | 8.x, 9.x | ✅ 支持 | 需要 EPEL repo |
| **CentOS** | 8 Stream | ⚠️ 可用 | CentOS 已停止维护 |
| **Debian** | 11, 12 | ⏳ 未测试 | 理论可行 |

#### 必需软件包

**Ubuntu/Debian**:
```bash
sudo apt-get update
sudo apt-get install -y \
    build-essential \
    git \
    python3 python3-pip \
    autoconf automake libtool \
    flex bison \
    libfl-dev \
    ccache \
    device-tree-compiler \
    libgmp-dev \
    libmpc-dev \
    libmpfr-dev \
    zlib1g-dev \
    texinfo
```

**RHEL/CentOS**:
```bash
sudo yum groupinstall -y "Development Tools"
sudo yum install -y \
    git \
    python3 python3-pip \
    autoconf automake libtool \
    flex bison \
    ccache \
    dtc \
    gmp-devel \
    libmpc-devel \
    mpfr-devel \
    zlib-devel \
    texinfo
```

---

### 1.3 Runner 软件配置

#### GitHub Actions Self-hosted Runner

```bash
# 1. 创建 runner 用户
sudo useradd -m -s /bin/bash github-runner
sudo usermod -aG sudo github-runner

# 2. 下载 runner 软件
cd /home/github-runner
curl -o actions-runner-linux-x64-2.311.0.tar.gz \
  -L https://github.com/actions/runner/releases/download/v2.311.0/actions-runner-linux-x64-2.311.0.tar.gz

# 3. 解压
tar xzf ./actions-runner-linux-x64-2.311.0.tar.gz

# 4. 配置 runner（需要 GitHub token）
./config.sh \
  --url https://github.com/openhwgroup/cva6 \
  --token <YOUR_TOKEN> \
  --name cva6-runner-1 \
  --labels self-hosted,linux,cva6,x64

# 5. 安装并启动 service
sudo ./svc.sh install github-runner
sudo ./svc.sh start

# 6. 验证状态
sudo ./svc.sh status
```

#### GitLab Runner

```bash
# 1. 安装 GitLab Runner（Ubuntu/Debian）
curl -L "https://packages.gitlab.com/install/repositories/runner/gitlab-runner/script.deb.sh" | sudo bash
sudo apt-get install gitlab-runner

# 2. 注册 runner
sudo gitlab-runner register \
  --url https://gitlab.com/ \
  --registration-token <YOUR_TOKEN> \
  --executor shell \
  --description "CVA6 CI Runner" \
  --tag-list "cva6,linux,shell"

# 3. 启动 runner
sudo gitlab-runner start

# 4. 验证
sudo gitlab-runner list
```

---

### 1.4 Runner 环境变量

创建 `/home/<runner>/.bashrc` 或 `/etc/profile.d/cva6-ci.sh`：

```bash
# CVA6 CI Environment

# RISC-V Toolchain
export RISCV=/opt/riscv-toolchain
export CV_SW_PREFIX=riscv64-unknown-elf-
export PATH=$RISCV/bin:$PATH

# Verilator
export VERILATOR_INSTALL_DIR=/opt/verilator
export PATH=$VERILATOR_INSTALL_DIR/bin:$PATH

# Spike
export SPIKE_INSTALL_DIR=/opt/spike
export SPIKE_PATH=$SPIKE_INSTALL_DIR/bin
export PATH=$SPIKE_PATH:$PATH

# 编译优化
export NUM_JOBS=16
export MAKEFLAGS="-j${NUM_JOBS}"

# 许可证服务器（如果需要）
export LM_LICENSE_FILE=27000@license-server.company.com

# ccache 加速
export PATH=/usr/lib/ccache:$PATH
export CCACHE_DIR=/data/ci/ccache
export CCACHE_MAXSIZE=50G
```

---

## 二、License 配置管理

### 2.1 License 类型和需求

| 工具 | License 类型 | 数量需求 | 优先级 |
|------|-------------|----------|--------|
| **Verilator** | 开源（Perl Artistic License） | N/A | N/A |
| **Spike** | 开源（BSD License） | N/A | N/A |
| **VCS** | 商业（Synopsys） | 2-5 并发 | 高 |
| **Questa/ModelSim** | 商业（Siemens） | 2-5 并发 | 高 |
| **DSim** | 商业（Metrics） | 2-5 并发 | 中 |
| **Verdi** | 商业（Synopsys） | 1-2 并发 | 低 |

---

### 2.2 License Server 配置

#### FlexLM License Server

**安装 License Server**:
```bash
# 1. 下载 Flex license manager（从 vendor 获取）
tar xzf flexlm-*.tar.gz
cd flexlm

# 2. 配置 license 文件
# 编辑 license.dat，添加 SERVER 和 VENDOR 行
cat > /opt/flexlm/license.dat << 'EOF'
SERVER license-server 001122334455 27000
VENDOR synopsys /opt/flexlm/synopsys
VENDOR siemens /opt/flexlm/siemens

# License keys (从 vendor 获取)
INCREMENT VCS synopsys 2024.06 ...
INCREMENT QUESTA siemens 2024.03 ...
EOF

# 3. 启动 license server
/opt/flexlm/lmgrd -c /opt/flexlm/license.dat -l /var/log/flexlm.log

# 4. 验证 license server
/opt/flexlm/lmstat -a -c 27000@license-server
```

**客户端配置**:
```bash
# Runner 上配置
export LM_LICENSE_FILE=27000@license-server.company.com

# 或者配置多个 license server（冗余）
export LM_LICENSE_FILE=27000@license1:27000@license2:27000@license3
```

---

### 2.3 License 检查清单

#### 每日检查

```bash
#!/bin/bash
# check-licenses.sh

# 检查 license server 状态
lmstat -a -c $LM_LICENSE_FILE > /tmp/license_status.txt

# 检查可用 license 数量
vcs_avail=$(grep "Users of VCS:" /tmp/license_status.txt | awk '{print $6}')
questa_avail=$(grep "Users of QUESTA:" /tmp/license_status.txt | awk '{print $6}')

# 告警阈值
if [ "$vcs_avail" -lt 2 ]; then
    echo "WARNING: VCS licenses running low ($vcs_avail available)"
    # 发送告警邮件
fi

if [ "$questa_avail" -lt 2 ]; then
    echo "WARNING: Questa licenses running low ($questa_avail available)"
fi
```

#### 每周检查

- [ ] License 是否即将过期（<30 天）
- [ ] License server 磁盘空间是否充足
- [ ] License 使用率统计（是否需要增加）

---

### 2.4 License 故障排查

#### 常见问题

| 问题 | 症状 | 解决方案 |
|------|------|----------|
| **License 不可用** | "License server down" | 重启 lmgrd |
| **License 超限** | "Maximum users reached" | 等待或增加 license |
| **License 过期** | "License expired" | 更新 license 文件 |
| **主机名不匹配** | "Invalid host" | 检查 SERVER 行 MAC 地址 |

#### 诊断命令

```bash
# 检查 license server 是否运行
lmstat -c $LM_LICENSE_FILE

# 查看哪些用户在使用 license
lmstat -a -c $LM_LICENSE_FILE | grep "Users of VCS"

# 查看特定用户的 license 使用
lmstat -a -c $LM_LICENSE_FILE | grep <username>

# 重启 license server（需要 sudo）
sudo pkill lmgrd
sudo /opt/flexlm/lmgrd -c /opt/flexlm/license.dat

# 查看 license server 日志
tail -f /var/log/flexlm.log
```

---

## 三、工具版本管理

### 3.1 工具版本锁定策略

#### 为什么需要版本锁定？

- ✅ **可重现性**: 确保 CI 结果一致
- ✅ **稳定性**: 避免工具升级带来的意外问题
- ✅ **兼容性**: 确保所有 runner 使用相同版本

#### 版本锁定方法

| 工具 | 锁定方法 | 版本文件 |
|------|----------|----------|
| **Verilator** | 固定 git tag | `verif/regress/install-verilator.sh` |
| **Spike** | 固定 git commit | `verif/regress/install-spike.sh` |
| **RISC-V Toolchain** | 固定 release 版本 | `ci/install-toolchain.sh` |
| **Python packages** | requirements.txt | `verif/sim/requirements.txt` |

---

### 3.2 当前推荐版本

| 工具 | 版本 | 发布日期 | 备注 |
|------|------|----------|------|
| **Verilator** | v5.008 | 2023-03-04 | 稳定版本 |
| **Spike** | 1.1.1-dev (commit 60e57248) | 2024-11 | CVA6 submodule 版本 |
| **GCC** | 13.1.0 | 2023-04-26 | RISC-V toolchain |
| **Python** | 3.8+ | - | 最低 3.8，推荐 3.10 |
| **VCS** | 2023.12 | 2023-12 | 商业仿真器 |
| **Questa** | 2023.4 | 2023-10 | 商业仿真器 |

---

### 3.3 版本验证脚本

```bash
#!/bin/bash
# verify-tools.sh - 验证所有工具版本

ERRORS=0

# 检查 Verilator
VERILATOR_VERSION=$(verilator --version | head -1)
if [[ ! "$VERILATOR_VERSION" =~ "5.008" ]]; then
    echo "ERROR: Verilator version mismatch. Expected 5.008, got $VERILATOR_VERSION"
    ((ERRORS++))
fi

# 检查 Spike
SPIKE_VERSION=$(spike --version | head -1)
if [[ ! "$SPIKE_VERSION" =~ "1.1.1-dev" ]]; then
    echo "ERROR: Spike version mismatch. Expected 1.1.1-dev, got $SPIKE_VERSION"
    ((ERRORS++))
fi

# 检查 GCC
GCC_VERSION=$($RISCV/bin/riscv64-unknown-elf-gcc --version | head -1)
if [[ ! "$GCC_VERSION" =~ "13.1.0" ]]; then
    echo "ERROR: GCC version mismatch. Expected 13.1.0, got $GCC_VERSION"
    ((ERRORS++))
fi

# 检查 Python
PYTHON_VERSION=$(python3 --version | awk '{print $2}')
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)
if [ "$PYTHON_MAJOR" -lt 3 ] || [ "$PYTHON_MINOR" -lt 8 ]; then
    echo "ERROR: Python version too old. Expected >=3.8, got $PYTHON_VERSION"
    ((ERRORS++))
fi

# 总结
if [ $ERRORS -eq 0 ]; then
    echo "✅ All tool versions correct"
    exit 0
else
    echo "❌ $ERRORS tool version mismatches found"
    exit 1
fi
```

---

## 四、Runner 监控和维护

### 4.1 监控指标

#### 关键指标

| 指标 | 监控方式 | 告警阈值 |
|------|----------|----------|
| **CPU 使用率** | `top`, `htop` | >90% for >30 min |
| **内存使用率** | `free -h` | >95% |
| **磁盘使用率** | `df -h` | >90% |
| **磁盘 I/O** | `iostat` | >80% util |
| **网络带宽** | `iftop`, `nload` | >80% link capacity |
| **Runner 状态** | GitLab/GitHub API | offline >5 min |

---

### 4.2 监控脚本示例

```bash
#!/bin/bash
# monitor-runner.sh - 监控 runner 健康状态

# 检查 CPU
CPU_USAGE=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d% -f1)
if (( $(echo "$CPU_USAGE > 90" | bc -l) )); then
    echo "WARNING: CPU usage high: $CPU_USAGE%"
fi

# 检查内存
MEM_USAGE=$(free | grep Mem | awk '{printf "%.0f", $3/$2 * 100}')
if [ "$MEM_USAGE" -gt 95 ]; then
    echo "WARNING: Memory usage high: $MEM_USAGE%"
fi

# 检查磁盘
DISK_USAGE=$(df -h / | tail -1 | awk '{print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -gt 90 ]; then
    echo "CRITICAL: Disk usage high: $DISK_USAGE%"
    # 清理临时文件
    find /tmp -type f -atime +7 -delete
fi

# 检查 runner service
if systemctl is-active --quiet github-actions.runner.*.service; then
    echo "✅ Runner service is running"
else
    echo "❌ Runner service is not running"
    # 尝试重启
    sudo systemctl restart github-actions.runner.*.service
fi
```

---

### 4.3 定期维护任务

#### 每日维护

```bash
# 清理旧的 artifacts
find /data/ci/artifacts -type f -mtime +7 -delete

# 清理 Docker images（如果使用）
docker system prune -af --filter "until=168h"

# 清理编译缓存（ccache）
ccache -C -M 50G

# 检查磁盘空间
df -h | grep -E '^/dev'
```

#### 每周维护

```bash
# 更新系统软件包（谨慎）
sudo apt-get update
sudo apt-get upgrade -y

# 检查 runner 日志
journalctl -u github-actions.runner.*.service --since "7 days ago" | grep ERROR

# 备份重要配置
tar czf /backup/runner-config-$(date +%Y%m%d).tar.gz \
    /home/github-runner/.github \
    /etc/profile.d/cva6-ci.sh

# 清理日志文件
find /var/log -name "*.log" -mtime +30 -delete
```

#### 每月维护

- [ ] 审查 license 使用情况
- [ ] 检查工具版本（是否需要升级）
- [ ] 审查磁盘空间趋势
- [ ] 更新文档（如果有变更）

---

## 五、故障排查清单

### 5.1 Runner 离线

#### 症状
- GitLab/GitHub 显示 runner status: offline
- Job 卡在 "pending" 状态

#### 排查步骤

```bash
# 1. 检查 runner service 状态
sudo systemctl status github-actions.runner.*.service
# 或
sudo gitlab-runner status

# 2. 检查网络连接
ping github.com
ping gitlab.com

# 3. 检查 runner 日志
journalctl -u github-actions.runner.*.service -n 100
# 或
sudo gitlab-runner run --debug

# 4. 重启 runner
sudo systemctl restart github-actions.runner.*.service
# 或
sudo gitlab-runner restart

# 5. 验证恢复
curl https://github.com/openhwgroup/cva6  # 确保能访问
```

---

### 5.2 磁盘空间不足

#### 症状
```
No space left on device
```

#### 快速清理脚本

```bash
#!/bin/bash
# emergency-cleanup.sh

echo "Cleaning up disk space..."

# 清理临时文件
find /tmp -type f -atime +1 -delete
find /var/tmp -type f -atime +1 -delete

# 清理 CVA6 编译文件
find /home/*/cva6 -name "*.o" -delete
find /home/*/cva6 -name "*.d" -delete
find /home/*/cva6/verif/sim -name "out_*" -exec rm -rf {} +

# 清理旧 artifacts
find /data/ci/artifacts -type f -mtime +3 -delete

# 清理 Docker（如果使用）
docker system prune -af

# 报告清理后空间
df -h
```

---

### 5.3 License 问题

#### 症状
```
Error: Failed to checkout license for VCS
Error: License server communication problem
```

#### 排查步骤

```bash
# 1. 检查 license server 连接
lmstat -c $LM_LICENSE_FILE

# 2. 检查 license 是否过期
lmutil lmdiag -c $LM_LICENSE_FILE

# 3. 检查哪些进程占用 license
lmstat -a -c $LM_LICENSE_FILE | grep "Users of VCS"

# 4. 测试 license checkout
vcs -help  # 如果能显示帮助，说明 license OK

# 5. 重启 license server（最后手段）
sudo pkill lmgrd
sudo /opt/flexlm/lmgrd -c /opt/flexlm/license.dat
```

---

### 5.4 性能问题

#### 症状
- CI 运行时间异常长
- CPU/内存占用持续很高

#### 诊断命令

```bash
# 查看最占 CPU 的进程
top -bn1 | head -20

# 查看最占内存的进程
ps aux --sort=-%mem | head -10

# 查看 I/O 等待
iostat -x 1 10

# 查看网络流量
iftop -i eth0

# 查看进程树（找出父进程）
pstree -p

# 查看特定进程的资源使用
pidstat -p <pid> 1 10
```

---

## 六、安全和权限管理

### 6.1 Runner 用户权限

#### 最小权限原则

```bash
# Runner 用户应该：
✅ 拥有 /home/<runner> 目录
✅ 可以执行编译和测试命令
✅ 可以访问必要的工具（verilator, spike, gcc）

# Runner 用户不应该：
❌ 拥有 sudo 权限（除非绝对必要）
❌ 访问其他用户的 home 目录
❌ 修改系统配置文件
```

#### 配置文件权限

```bash
# 确保敏感文件权限正确
chmod 600 /home/github-runner/.github/credentials
chmod 600 /opt/flexlm/license.dat
chmod 700 /home/github-runner/.ssh
```

---

### 6.2 访问控制

#### GitLab Runner Tags

使用 tags 限制哪些 job 可以运行：

```yaml
# .gitlab-ci.yml

vcs-tests:
  tags:
    - cva6       # 只在 cva6 tagged runner 运行
    - vcs        # 只在有 VCS license 的 runner 运行
  script:
    - make vcs-testharness
```

#### GitHub Actions Labels

```yaml
# .github/workflows/ci.yml

jobs:
  build:
    runs-on: [self-hosted, linux, cva6, vcs]  # 多标签匹配
```

---

### 6.3 Secrets 管理

#### GitLab CI/CD Variables

在 GitLab 项目设置中配置 secrets：

```
Settings → CI/CD → Variables

LM_LICENSE_FILE = 27000@license-server (Protected, Masked)
VCS_HOME = /opt/synopsys/vcs (Protected)
```

#### GitHub Secrets

在 GitHub 仓库设置中配置：

```
Settings → Secrets and variables → Actions

LM_LICENSE_FILE = 27000@license-server
```

**使用方式**:
```yaml
- name: Run VCS tests
  env:
    LM_LICENSE_FILE: ${{ secrets.LM_LICENSE_FILE }}
  run: make vcs-testharness
```

---

## 七、总结

### 7.1 快速参考卡

**Runner 健康检查（5 分钟）**:
```bash
# 1. Runner service 状态
sudo systemctl status github-actions.runner.*.service

# 2. 磁盘空间
df -h

# 3. License 可用性
lmstat -a -c $LM_LICENSE_FILE | grep "Users of"

# 4. 工具版本
verilator --version
spike --version
$RISCV/bin/riscv64-unknown-elf-gcc --version
```

---

### 7.2 每日检查清单

**CI 维护者每日必做**:
- [ ] 检查 runner 是否 online
- [ ] 检查磁盘使用率 (<90%)
- [ ] 检查 license 可用数量
- [ ] Review overnight regression 结果
- [ ] 清理超过 7 天的 artifacts

---

### 7.3 故障联系方式

| 问题类型 | 联系人 | 响应时间 |
|----------|--------|----------|
| **Runner 离线** | CI Team | 1 小时 |
| **License 问题** | License Admin | 2 小时 |
| **网络问题** | IT Support | 4 小时 |
| **硬件故障** | Data Center | 1 天 |

---

**相关文档**:
- [WEEK1_EXECUTION_GUIDE.md](./WEEK1_EXECUTION_GUIDE.md) - 本地环境配置
- [03_how_ci_runs_end_to_end.md](./03_how_ci_runs_end_to_end.md) - CI 执行流程
- [06_ci_triage_playbook.md](./06_ci_triage_playbook.md) - CI 故障排查
