# 术语表（Glossary）

**文档版本**: v1.0
**创建日期**: 2026-01-18
**维护者**: OpenHW CI Team
**目标读者**: 所有 CVA6 项目参与者

---

## 文档目的

本文档提供 **CVA6 CI/Regression 相关术语的完整索引**，包括：
- 📖 CI/CD 术语（中英文对照）
- 🔧 RISC-V 术语
- 💻 CVA6 特定术语
- 🛠️ 工具和命令速查

---

## 目录

1. [CI/CD 术语](#一cicd-术语)
2. [RISC-V 术语](#二risc-v-术语)
3. [CVA6 架构术语](#三cva6-架构术语)
4. [测试和验证术语](#四测试和验证术语)
5. [工具和仿真器](#五工具和仿真器)
6. [命令和脚本](#六命令和脚本)
7. [缩写词索引](#七缩写词索引)

---

## 一、CI/CD 术语

### A

**Artifact** (产物)
- **定义**: CI pipeline 生成的文件，如编译的二进制、测试日志、coverage 报告
- **示例**: `test_results.xml`, `coverage.ucdb`, `verilator_binary.tar.gz`
- **使用**: GitLab/GitHub Actions 的 artifacts 功能

**Assertion** (断言)
- **定义**: RTL 代码中的检查语句，用于验证设计不变式
- **示例**: `assert (lsu_valid && lsu_ready) || !lsu_req`
- **用途**: 在仿真时捕获设计违规

**ASIC** (Application-Specific Integrated Circuit，专用集成电路)
- **定义**: 为特定应用设计的芯片
- **对比**: FPGA（可重编程）vs ASIC（固定功能）

---

### B

**Benchmark** (基准测试)
- **定义**: 标准化的性能测试程序
- **示例**: CoreMark, Dhrystone, SPEC CPU
- **用途**: 评估 CPU 性能，检测性能回归

**Bisect** (二分查找)
- **定义**: Git bisect，通过二分法找到引入 bug 的 commit
- **命令**: `git bisect start/good/bad`
- **用途**: 回归问题定位

**Branch Coverage** (分支覆盖率)
- **定义**: 代码中所有分支（if/else）被执行的比例
- **计算**: (执行的分支数 / 总分支数) × 100%
- **目标**: CVA6 目标 >85%

---

### C

**Cache** (缓存)
- **CI 上下文**: 保存编译好的工具链、依赖，加速 CI
- **示例**: GitHub Actions cache，GitLab CI cache
- **键（Key）**: 基于文件 hash，如 `${{ hashFiles('Makefile') }}`

**CI (Continuous Integration，持续集成)**
- **定义**: 自动化地频繁集成代码变更并运行测试
- **目的**: 尽早发现集成问题
- **工具**: GitLab CI, GitHub Actions, Jenkins

**CD (Continuous Deployment/Delivery，持续部署/交付)**
- **定义**: 自动化地将代码部署到生产环境
- **区别**: Delivery（手动批准）vs Deployment（全自动）

**Code Coverage** (代码覆盖率)
- **定义**: 测试执行的代码行数占总代码的比例
- **类型**: Line, Branch, FSM, Toggle, Functional
- **目标**: CVA6 目标 >90% line coverage

**Coverage Closure** (覆盖率闭环)
- **定义**: 通过添加测试达到 coverage 目标的过程
- **步骤**: 分析未覆盖代码 → 编写测试 → 验证覆盖率提升

---

### D

**Dashboard** (仪表板)
- **定义**: 可视化 CI 状态和指标的 Web 界面
- **内容**: 测试通过率、coverage 趋势、失败测试统计
- **工具**: Grafana, GitLab Pages, GitHub Pages

**DUT (Design Under Test，被测设计)**
- **定义**: 正在测试的 RTL 设计
- **CVA6 上下文**: CVA6 CPU core

**DV (Design Verification，设计验证)**
- **定义**: 验证 RTL 设计功能正确性的过程
- **方法**: 仿真、形式验证、FPGA 原型

---

### E

**Escalation** (升级)
- **定义**: 将问题升级到更高级别的支持
- **触发**: 无法自行解决，影响面大，优先级高
- **流程**: 见 [06_ci_triage_playbook.md](./06_ci_triage_playbook.md) § 5

---

### F

**Flaky Test** (不稳定测试)
- **定义**: 同样的代码，有时 PASS 有时 FAIL 的测试
- **原因**: Timing 竞争、随机种子、资源竞争
- **处理**: 固定随机种子、增加超时、标记为 known failure

**FSM (Finite State Machine，有限状态机)**
- **定义**: 由状态和状态转移组成的模型
- **Coverage**: FSM coverage 衡量所有状态和转移是否被访问
- **目标**: CVA6 目标 >95%

**Functional Coverage** (功能覆盖率)
- **定义**: 功能点被测试到的比例
- **定义方式**: SystemVerilog covergroup
- **vs Code Coverage**: Functional 关注"做了什么"，Code 关注"执行了哪些行"

---

### G

**GitLab CI**
- **定义**: GitLab 内置的 CI/CD 系统
- **配置文件**: `.gitlab-ci.yml`
- **特点**: 强大的 pipeline 管理，适合复杂流程

**GitHub Actions**
- **定义**: GitHub 内置的 CI/CD 系统
- **配置文件**: `.github/workflows/*.yml`
- **特点**: 简单易用，社区 actions 丰富

---

### J

**Job**
- **定义**: CI pipeline 中的一个执行单元
- **示例**: `build-riscv-tests`, `execute-riscv64-tests`
- **并行**: 多个 jobs 可以并行运行

**JUnit XML**
- **定义**: 标准的测试结果格式
- **用途**: GitLab/GitHub 可以解析并显示测试结果
- **格式**: `<testsuites><testsuite><testcase>...</testcase></testsuite></testsuites>`

---

### L

**License**
- **类型**: 开源（MIT, BSD, GPL）vs 商业（VCS, Questa）
- **管理**: FlexLM license server
- **检查**: `lmstat -a -c $LM_LICENSE_FILE`

**Line Coverage** (行覆盖率)
- **定义**: 被执行的代码行数 / 总代码行数
- **目标**: CVA6 目标 >90%

**Lint**
- **定义**: 静态代码检查工具
- **功能**: 检测语法错误、风格问题、潜在 bug
- **工具**: Verilator --lint-only, Synopsys SpyGlass

---

### M

**Matrix** (矩阵)
- **定义**: GitHub Actions/GitLab CI 的并行测试策略
- **示例**: `matrix: {config: [A, B], test: [X, Y]}` 生成 A-X, A-Y, B-X, B-Y 4 个 jobs
- **用途**: 多配置并行测试

**MTTR (Mean Time To Repair，平均修复时间)**
- **定义**: 从 CI 失败到修复的平均时间
- **目标**: <24 小时
- **提升方法**: 自动化诊断、清晰的错误信息

---

### N

**Nightly Regression** (每晚回归)
- **定义**: 每天自动运行的完整测试集
- **时间**: 通常在夜间（00:00）运行
- **测试数**: CVA6 ~800 tests, 4-6 小时

---

### P

**Pipeline**
- **定义**: CI 系统的执行流程，由多个 stages/jobs 组成
- **示例**: setup → build → test → report
- **状态**: pending, running, success, failed

**PR (Pull Request，拉取请求)**
- **GitHub 术语**: PR
- **GitLab 术语**: MR (Merge Request)
- **用途**: 代码审查和合并的机制

---

### R

**Regression** (回归)
- **定义**: 新代码破坏了原本工作的功能
- **检测**: 回归测试（重新运行所有历史测试）
- **预防**: 完善的 CI 系统

**Regression Test** (回归测试)
- **定义**: 确保新代码不破坏现有功能的测试
- **CVA6**: riscv-tests, riscv-arch-test

**Runner**
- **定义**: 执行 CI jobs 的机器
- **类型**: GitHub-hosted（云端）vs Self-hosted（自建）
- **CVA6**: 使用 self-hosted runners（需要 VCS/Questa license）

---

### S

**Sanity Test** = **Smoke Test**

**SLA (Service Level Agreement，服务等级协议)**
- **定义**: CI 系统承诺的性能指标
- **示例**: PR smoke test <30 分钟（P95）
- **详见**: [05_ci_contract.md](./05_ci_contract.md) § 3

**Smoke Test** (冒烟测试)
- **定义**: 快速验证基础功能的最小测试集
- **目的**: 尽早发现明显问题
- **CVA6**: ~50 tests, 20-30 分钟

**Stage**
- **定义**: GitLab CI pipeline 的阶段
- **示例**: setup → light tests → heavy tests → report
- **顺序**: 前一个 stage 完成后才运行下一个

---

### T

**Tandem Simulation** (串联仿真)
- **定义**: RTL 和 ISS（如 Spike）同时运行，逐周期比对
- **目的**: 确保 RTL 和 ISS 行为一致
- **CVA6**: 通过 RVFI 接口实现

**Testbench**
- **定义**: 用于驱动和检查 DUT 的测试环境
- **类型**: APU testbench（轻量）vs UVM testbench（完整）
- **CVA6**: `verif/tb/core/`

**Testlist**
- **定义**: YAML 文件，列出要运行的测试
- **位置**: `verif/tests/testlist_*.yaml`
- **字段**: test, iterations, rtl_test, iss, timeout

**Timeout** (超时)
- **定义**: 测试运行时间超过阈值
- **原因**: 死循环、性能问题、卡死
- **处理**: 增加超时时间或优化测试

**Toggle Coverage** (翻转覆盖率)
- **定义**: 信号从 0→1 和 1→0 翻转的覆盖率
- **用途**: 检测未使用的信号、常数优化

---

### U

**Uptime**
- **定义**: 系统正常运行时间占比
- **计算**: (正常运行时间 / 总时间) × 100%
- **目标**: CI系统 99% uptime

---

### W

**Weekly Regression** (每周回归)
- **定义**: 每周运行的最完整测试集
- **时间**: 周日 00:00
- **测试数**: CVA6 1200+ tests, 8-12 小时
- **Coverage**: 收集 coverage

**Workflow**
- **定义**: GitHub Actions 的 pipeline
- **配置文件**: `.github/workflows/*.yml`
- **触发**: push, pull_request, schedule, workflow_dispatch

---

## 二、RISC-V 术语

### A

**ABI (Application Binary Interface，应用二进制接口)**
- **定义**: 定义函数调用、寄存器使用约定
- **RISC-V ABIs**: `ilp32` (RV32), `lp64` (RV64), `lp64d` (RV64 + hard float)

**AMO (Atomic Memory Operation，原子内存操作)**
- **指令**: `amoadd.w`, `amoswap.d`, `lr.w`, `sc.d`
- **扩展**: A 扩展（Atomic）
- **用途**: 多核同步、无锁数据结构

**APU (Application Processing Unit，应用处理单元)**
- **CVA6 上下文**: APU testbench = 轻量级 testbench，仅测试 CPU 核心
- **vs UVM**: APU 更简单，UVM 更完整

**Arch Test** = **RISC-V Architecture Test**
- **来源**: https://github.com/riscv-non-isa/riscv-arch-test
- **用途**: 验证 RISC-V 实现符合规范

---

### C

**CSR (Control and Status Register，控制和状态寄存器)**
- **定义**: RISC-V 特权架构的配置和状态寄存器
- **示例**: `mstatus`, `mtvec`, `mcause`, `mscratch`
- **访问**: `csrrw`, `csrrs`, `csrrc`, `csrrwi`, `csrrsi`, `csrrci`

**CV-X-IF (Core-V eXtension Interface)**
- **定义**: CVA6 的自定义扩展接口
- **用途**: 连接协处理器、加速器
- **别名**: CVXIF

---

### E

**Exception** (异常)
- **定义**: 指令执行过程中的错误或事件
- **类型**: Illegal instruction, Load/Store misalignment, Breakpoint
- **处理**: 跳转到 `mtvec` 指向的 handler

**Extension** (扩展)
- **RISC-V 模块化设计**: 基础 ISA (I) + 可选扩展
- **常见扩展**:
  - **I**: Integer（整数）
  - **M**: Multiplication/Division（乘除法）
  - **A**: Atomic（原子操作）
  - **F**: Single-precision Float（单精度浮点）
  - **D**: Double-precision Float（双精度浮点）
  - **C**: Compressed（压缩指令，16-bit）
  - **S**: Supervisor mode（监督者模式）
  - **H**: Hypervisor（虚拟化）

---

### F

**FPGA (Field-Programmable Gate Array，现场可编程门阵列)**
- **用途**: 原型验证、软件开发
- **CVA6 支持**: Genesys2, VC707, VCU128

**FPU (Floating-Point Unit，浮点运算单元)**
- **扩展**: F（单精度）+ D（双精度）
- **CVA6**: 集成 FPU，支持 F/D 扩展

---

### H

**Hart (Hardware Thread，硬件线程)**
- **定义**: RISC-V 术语中的"核心"或"硬件线程"
- **CVA6**: 单核 = 1 hart

**HPDCache (High-Performance Data Cache)**
- **定义**: CVA6 的高性能数据缓存
- **特点**: Write-back, Write-allocate
- **配置**: `cv64a6_imafdc_sv39_hpdcache`

---

### I

**Interrupt** (中断)
- **类型**: Timer interrupt, Software interrupt, External interrupt
- **CSR**: `mie` (enable), `mip` (pending), `mtvec` (handler)

**ISA (Instruction Set Architecture，指令集架构)**
- **定义**: CPU 支持的指令集合
- **CVA6**: RV64IMAFDC（64-bit, I/M/A/F/D/C 扩展）

**ISS (Instruction Set Simulator，指令集仿真器)**
- **定义**: 软件仿真 RISC-V 指令执行
- **CVA6 使用**: Spike
- **用途**: Tandem simulation（与 RTL 比对）

---

### M

**Machine Mode** (M-mode，机器模式)
- **定义**: RISC-V 最高特权级
- **用途**: 启动代码、异常处理、硬件访问
- **CSR 前缀**: `m` (如 `mstatus`, `mtvec`)

**Memory-Mapped I/O** (MMIO，内存映射 I/O)
- **定义**: 通过 Load/Store 指令访问外设
- **地址空间**: CVA6 0x10000000 - 0x1FFFFFFF（CLINT, PLIC, UART）

---

### P

**Physical Memory Protection (PMP)**
- **定义**: M-mode 配置的内存访问权限
- **CSR**: `pmpcfg*`, `pmpaddr*`
- **用途**: 限制 S-mode/U-mode 内存访问范围

**Privileged Architecture** (特权架构)
- **定义**: RISC-V 的特权级定义（M/S/U mode）
- **规范**: RISC-V Privileged ISA Specification
- **CVA6**: 支持 M-mode 和 S-mode

---

### R

**RISC-V**
- **全称**: Reduced Instruction Set Computer - V (第五代)
- **特点**: 开源、模块化、可扩展
- **网站**: https://riscv.org

**RVFI (RISC-V Formal Interface)**
- **定义**: RISC-V 核心和 verification 工具的接口
- **用途**: 形式验证、tandem simulation
- **CVA6**: 实现 RVFI，连接 Spike

**RV32 / RV64**
- **RV32**: 32-bit RISC-V
- **RV64**: 64-bit RISC-V
- **CVA6**: 主要是 RV64（也有 RV32 配置）

---

### S

**Spike**
- **定义**: RISC-V 官方 ISS (Instruction Set Simulator)
- **来源**: https://github.com/riscv/riscv-isa-sim
- **用途**: CVA6 tandem simulation 的 golden reference

**Supervisor Mode** (S-mode，监督者模式)
- **定义**: 运行操作系统内核的特权级
- **权限**: 低于 M-mode，高于 U-mode
- **CSR 前缀**: `s` (如 `sstatus`, `stvec`)

**Sv32 / Sv39 / Sv48**
- **定义**: RISC-V 虚拟内存方案
- **Sv39**: 39-bit 虚拟地址（3 级页表），RV64 常用
- **CVA6**: 支持 Sv39

---

### U

**User Mode** (U-mode，用户模式)
- **定义**: 最低特权级，运行应用程序
- **限制**: 不能访问 CSR、不能执行特权指令

---

### X

**XLEN**
- **定义**: RISC-V 寄存器位宽
- **值**: 32 (RV32), 64 (RV64)
- **CVA6**: XLEN=64

---

## 三、CVA6 架构术语

### A

**Ariane**
- **历史**: CVA6 的前身名称（苏黎世联邦理工学院开发）
- **更名**: 2020 年更名为 CVA6（Core-V Application 6-stage）

---

### C

**Core-V**
- **定义**: OpenHW Group 的 RISC-V 核心系列
- **成员**: CV32E40P (32-bit), CVA6 (64-bit), CVA5 (32-bit 5-stage)

**CVA6**
- **全称**: Core-V Application 6-stage
- **特点**: 6级流水线、单发射、顺序执行
- **配置**: cv64a6_imafdc_sv39（64-bit, IMAFDC 扩展, Sv39 虚拟内存）

**cv64a6_imafdc_sv39**
- **定义**: CVA6 的默认 64-bit 配置
- **含义**:
  - `cv64a6`: Core-V Application 64-bit 6-stage
  - `imafdc`: RISC-V 扩展（I/M/A/F/D/C）
  - `sv39`: Sv39 虚拟内存

**cv32a6_imac_sv0**
- **定义**: CVA6 的 32-bit 配置
- **含义**:
  - `cv32a6`: 32-bit 配置
  - `imac`: I/M/A/C 扩展（无浮点）
  - `sv0`: 无虚拟内存

---

### F

**Frontend**
- **定义**: 取指模块（Instruction Fetch）
- **CVA6 路径**: `core/frontend/`
- **功能**: 分支预测、取指缓存（ICache）

---

### L

**LSU (Load-Store Unit)**
- **定义**: Load/Store 执行单元
- **CVA6 路径**: `core/load_store_unit.sv`
- **功能**: 地址计算、数据缓存访问、PMP 检查

---

### P

**PTW (Page Table Walker)**
- **定义**: 页表遍历单元
- **用途**: 虚拟地址 → 物理地址转换
- **CVA6 路径**: `core/mmu_sv39/ptw.sv`

---

### W

**Write-back** (WB，写回)
- **Cache 策略**: 修改的数据先写回 cache，稍后写回内存
- **vs Write-through**: Write-through 立即写回内存
- **CVA6**: HPDCache 使用 write-back

---

## 四、测试和验证术语

### B

**Bug**
- **定义**: RTL 设计或验证环境中的错误
- **分类**:
  - **RTL Bug**: 设计功能错误
  - **Testbench Bug**: 验证环境错误
  - **Tool Bug**: 仿真器/编译器错误

---

### C

**Corner Case** (边界情况)
- **定义**: 极端或罕见的输入组合
- **示例**: 除以零、最大/最小值、同时发生的事件
- **重要性**: 常常是 bug 隐藏的地方

**Constrained Random** (约束随机)
- **定义**: UVM 中的随机测试，带有约束条件
- **示例**: `randomize(addr) with {addr >= 0x8000_0000; addr < 0x9000_0000;}`
- **用途**: 自动生成大量测试用例

---

### D

**Directed Test** (定向测试)
- **定义**: 手工编写的、针对特定功能的测试
- **vs Random Test**: Directed 精确控制，Random 覆盖广

---

### G

**Golden Reference** (黄金参考)
- **定义**: 正确的参考实现
- **CVA6**: Spike 是 golden reference
- **用途**: RTL 和 Spike 的结果必须一致

---

### M

**Mismatch**
- **定义**: RTL 和 ISS 的结果不一致
- **示例**: RTL 计算 5+3=8，Spike 计算 5+3=9 → Mismatch
- **处理**: 检查 RTL bug 或 ISS 版本不匹配

---

### S

**Self-checking** (自检)
- **定义**: 测试自动判断 PASS/FAIL，无需人工查看
- **实现**: 测试程序内置检查逻辑
- **好处**: 可自动化回归

---

### T

**Trace** (波形)
- **定义**: 仿真过程中所有信号的时间序列
- **格式**: VCD, FST（压缩）, WLF（Questa）
- **工具**: GTKWave, Verdi, Questa GUI

**Triage** (分诊)
- **定义**: 对 CI 失败进行分类和优先级排序
- **流程**: 见 [06_ci_triage_playbook.md](./06_ci_triage_playbook.md)

---

## 五、工具和仿真器

### C

**ccache**
- **定义**: C/C++ 编译缓存工具
- **用途**: 加速重复编译
- **CVA6 使用**: `export PATH=/usr/lib/ccache:$PATH`

---

### D

**DSim**
- **开发商**: Metrics
- **类型**: 商业仿真器
- **特点**: 高性能，支持 UVM
- **CVA6 计划**: Week 3 集成

---

### G

**GCC (GNU Compiler Collection)**
- **RISC-V 版本**: riscv64-unknown-elf-gcc, riscv32-unknown-elf-gcc
- **用途**: 编译 C/C++ 测试程序
- **CVA6 推荐**: GCC 13.1.0

**GTKWave**
- **定义**: 开源波形查看器
- **支持格式**: VCD, FST, GHW
- **命令**: `gtkwave trace.fst &`

---

### Q

**Questa / QuestaSim**
- **开发商**: Siemens (原 Mentor Graphics)
- **类型**: 商业仿真器
- **特点**: 完整 UVM 支持，coverage 收集
- **别名**: ModelSim（Questa 的前身）

---

### S

**Spike** (见 [二、RISC-V 术语](#spike))

**Synopsys**
- **公司**: Synopsys Inc.
- **产品**: VCS (仿真器), Verdi (波形工具), Design Compiler (综合)

---

### V

**VCS (Verilog Compiler Simulator)**
- **开发商**: Synopsys
- **类型**: 商业仿真器
- **特点**: 高性能，coverage 收集，形式验证
- **CVA6 使用**: Nightly/Weekly regression

**Verilator**
- **定义**: 开源 Verilog 仿真器
- **特点**: 高速（编译为 C++），免费
- **推荐版本**: v5.008
- **CVA6 使用**: PR smoke test

**Verdi**
- **定义**: Synopsys 的波形和调试工具
- **特点**: 强大的波形分析、源码追踪
- **格式**: FSDB (Fast Signal Database)

---

### X

**Xcelium**
- **开发商**: Cadence
- **类型**: 商业仿真器
- **CVA6 使用**: GitLab CI 部分 job

---

## 六、命令和脚本

### B

**`bash`**
- Shell 脚本语言
- CVA6 回归脚本：`bash verif/regress/smoke-tests-*.sh`

---

### G

**`git bisect`**
- 二分查找引入 bug 的 commit
- 用法：`git bisect start/good/bad`

**`git submodule`**
- 管理 Git 子模块
- 初始化：`git submodule update --init --recursive`

**`grep`**
- 文本搜索
- CI 日志分析：`grep -E "ERROR|FAIL" logfile.log`

**`gtkwave`**
- 波形查看
- 命令：`gtkwave trace.fst &`

---

### L

**`lmstat`**
- 查看 FlexLM license 状态
- 用法：`lmstat -a -c $LM_LICENSE_FILE`

---

### M

**`make`**
- 构建工具
- CVA6 仿真：`make veri-testharness`

---

### P

**`python3 cva6.py`**
- CVA6 测试执行脚本
- 位置：`verif/sim/cva6.py`
- 用法：`python3 cva6.py --target <target> --iss <iss> --test <test>`

---

### S

**`source`**
- 执行脚本并设置环境变量
- CVA6 环境：`source verif/sim/setup-env.sh`

**`spike`**
- RISC-V ISS
- 用法：`spike --isa=RV64IMAFDC pk <elf_file>`

---

### V

**`verilator`**
- Verilator 仿真器
- 编译：`verilator --cc core.sv`
- Lint：`verilator --lint-only core.sv`

**`vcover`**
- Questa coverage 工具
- 合并：`vcover merge -out merged.ucdb test1.ucdb test2.ucdb`
- 报告：`vcover report -html -htmldir cov_html merged.ucdb`

**`vcs`**
- VCS 仿真器
- 编译：`vcs -sverilog core.sv`

---

## 七、缩写词索引

| 缩写 | 全称 | 中文 |
|------|------|------|
| **ABI** | Application Binary Interface | 应用二进制接口 |
| **ALU** | Arithmetic Logic Unit | 算术逻辑单元 |
| **AMO** | Atomic Memory Operation | 原子内存操作 |
| **APU** | Application Processing Unit | 应用处理单元 |
| **ASIC** | Application-Specific Integrated Circuit | 专用集成电路 |
| **BHT** | Branch History Table | 分支历史表 |
| **BTB** | Branch Target Buffer | 分支目标缓冲 |
| **CI** | Continuous Integration | 持续集成 |
| **CD** | Continuous Deployment/Delivery | 持续部署/交付 |
| **CSR** | Control and Status Register | 控制和状态寄存器 |
| **CVA6** | Core-V Application 6-stage | Core-V 应用级 6 级流水线 |
| **CVXIF** | Core-V eXtension Interface | Core-V 扩展接口 |
| **DUT** | Design Under Test | 被测设计 |
| **DV** | Design Verification | 设计验证 |
| **FPGA** | Field-Programmable Gate Array | 现场可编程门阵列 |
| **FPU** | Floating-Point Unit | 浮点运算单元 |
| **FSM** | Finite State Machine | 有限状态机 |
| **HPDCache** | High-Performance Data Cache | 高性能数据缓存 |
| **ICache** | Instruction Cache | 指令缓存 |
| **ISA** | Instruction Set Architecture | 指令集架构 |
| **ISS** | Instruction Set Simulator | 指令集仿真器 |
| **LSU** | Load-Store Unit | Load/Store 单元 |
| **MMIO** | Memory-Mapped I/O | 内存映射 I/O |
| **MTTR** | Mean Time To Repair | 平均修复时间 |
| **PC** | Program Counter | 程序计数器 |
| **PMP** | Physical Memory Protection | 物理内存保护 |
| **PR** | Pull Request | 拉取请求 |
| **PTW** | Page Table Walker | 页表遍历单元 |
| **RVFI** | RISC-V Formal Interface | RISC-V 形式接口 |
| **SLA** | Service Level Agreement | 服务等级协议 |
| **TLB** | Translation Lookaside Buffer | 地址转换后备缓冲器 |
| **UVM** | Universal Verification Methodology | 通用验证方法学 |
| **VCS** | Verilog Compiler Simulator | Verilog 编译仿真器 |

---

## 八、快速查找

### 按字母顺序

A-D: [AMO](#amo-atomic-memory-operation原子内存操作), [Artifact](#artifact-产物), [Assertion](#assertion-断言), [Benchmark](#benchmark-基准测试), [CI](#ci-continuous-integration持续集成), [Coverage](#code-coverage-代码覆盖率), [CSR](#csr-control-and-status-register控制和状态寄存器), [CVA6](#cva6), [DUT](#dut-design-under-test被测设计)

E-H: [Exception](#exception-异常), [FPGA](#fpga-field-programmable-gate-array现场可编程门阵列), [FSM](#fsm-finite-state-machine有限状态机), [Hart](#hart-hardware-thread硬件线程), [HPDCache](#hpdcache-high-performance-data-cache)

I-L: [ISA](#isa-instruction-set-architecture指令集架构), [ISS](#iss-instruction-set-simulator指令集仿真器), [License](#license), [LSU](#lsu-load-store-unit)

M-P: [Matrix](#matrix-矩阵), [Mismatch](#mismatch), [Nightly](#nightly-regression-每晚回归), [Pipeline](#pipeline), [PMP](#physical-memory-protection-pmp), [PTW](#ptw-page-table-walker)

Q-T: [Questa](#questa--questasim), [Regression](#regression-回归), [RVFI](#rvfi-risc-v-formal-interface), [Smoke Test](#smoke-test-冒烟测试), [Spike](#spike), [Tandem](#tandem-simulation-串联仿真), [Testbench](#testbench)

U-Z: [UVM](#), [VCS](#vcs-verilog-compiler-simulator), [Verilator](#verilator), [Weekly](#weekly-regression-每周回归)

---

## 总结

本术语表涵盖了 CVA6 CI/Regression 系统的所有关键术语。建议：
- **新人**: 从 CI/CD 术语开始阅读
- **验证工程师**: 重点看测试和验证术语
- **CI 维护者**: 重点看工具和命令
- **遇到不认识的术语**: 使用浏览器搜索功能（Ctrl+F）

---

**相关文档**:
- [01_ci_for_beginners.md](./01_ci_for_beginners.md) - CI 基础概念详解
- [02_current_cva6_ci_inventory.md](./02_current_cva6_ci_inventory.md) - 现有 CI 配置详解
- [00_README.md](./00_README.md) - 文档导航
