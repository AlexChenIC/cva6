# CVA6 APU Verilator CI 扩展项目说明文档

本文档旨在详细介绍 `ci/openhw/aws` 目录下新 CI 体系的设计思路、使用方法及未来维护指南。

## 1. 项目目的 (Objective)

本工作的核心目标是为 CVA6 APU 构建一个**模块化**、**可移植**且**易于扩展**的持续集成（CI）验证流程。

具体痛点与解决目标：
*   **解耦**：将 GitHub Actions 的 YAML 逻辑与具体的 Shell 脚本实现分离。这使得同一个测试脚本既可以在 GitHub 上跑，也可以在未来的 AWS Self-hosted Runner 或本地开发者机器上直接运行，方便调试。
*   **多仿真器准备**：虽然目前仅支持 Verilator，但脚本架构设计之初就考虑了 DSim、Questasim 等商业 EDA 工具的接入接口。
*   **统一入口**：通过统一的入口脚本管理复杂的测试配置（32/64位、不同测试集），降低使用门槛。
*   **全面回归**：以 Verilator 为主的 CI 目标是覆盖尽可能多的已有 testcases，确保对核心功能的回归能力。

## 2. 必备背景知识 (Prerequisites)

为了理解和维护这套系统，您需要了解以下概念：

*   **CVA6 架构**：了解 CVA6 是支持 RISC-V 32位和64位的处理器核，以及它依赖 `verif/core-v-verif` 等子模块。
*   **验证环境**：
    *   **Verilator**：开源的 Verilog 仿真器，将 Verilog 转换为 C++ 进行模拟。
    *   **Spike**：RISC-V 的指令集模拟器（ISS），常用于 Tandem Verification（协同仿真），即作为“黄金标准”与 CVA6 的执行结果进行比对。
    *   **core-v-verif 子模块**：包含部分验证资产与工具依赖，是多套回归脚本的基础。
*   **CI 基础**：
    *   **GitHub Actions**：利用 `.github/workflows` 定义的自动化流程。
    *   **Runner**：执行 CI 任务的机器（目前是 GitHub 提供的 Ubuntu 虚拟机，未来可能是 AWS 上的自定义机器）。

## 3. 参考内容 (References)

本系统的设计参考并复用了项目中已有的核心资产：

*   **CI 配置文件**：`.github/workflows/ci.yml`（参考其缓存机制和基本流程）。
*   **官方回归脚本**：`verif/regress/*.sh`（官方维护的回归入口，优先与其保持一致）。
*   **仿真环境脚本**：`verif/sim/setup-env.sh`（标准化环境变量与工具路径）。

## 4. 文件详解 (File Descriptions)

我们在 `ci/openhw/aws` 目录下构建了一套分层架构：

### 4.1. `env_setup.sh` (环境层)
*   **作用**：检测运行环境（是 GitHub 还是本地），并导出全局环境变量（如 `RISCV`, `VERILATOR_ROOT`）。
*   **目的**：解决路径依赖问题，并让工具目录与 CI 缓存保持一致。未来如果切换到 AWS，只需修改此文件中的路径定义，无需改动上层脚本。

### 4.2. `build_infrastructure.sh` (构建层)
*   **作用**：安装系统依赖、Python 依赖，并统一调用 `verif/regress/install-*.sh` 来构建 Verilator 和 Spike，保证与官方回归流程一致。
*   **目的**：封装构建逻辑，确保测试运行前环境是就绪的，并与缓存目录 (`tools/`) 对齐。

### 4.3. `run_verification.sh` (执行层)
*   **作用**：最底层的执行器。接受 `Target Config`（配置）、`Test Script`（脚本名）和 `Simulator`（仿真器）三个参数，配置好仿真环境后调用 `verif/regress/` 下的具体脚本。
*   **目的**：统一所有仿真器的调用接口。Verilator 特有的 `SPIKE_TANDEM` 逻辑也在此处处理。

### 4.4. `run_test_suite.sh` (调度层)
*   **作用**：用户友好的前端接口。将简单的测试套件名称（如 `smoke`, `arch`, `benchmarks`）映射到具体的复杂脚本文件。
*   **目的**：简化 CI 配置文件，并根据配置（32位或64位）自动选择正确的测试脚本。

### 4.5. `.github/workflows/verilator-apu-ci.yml` (CI 配置)
*   **作用**：GitHub Actions 的入口文件。定义了 `matrix`（矩阵），并行运行多种配置和测试套件的组合。
*   **目的**：自动化触发上述脚本。

## 5. 本次新增/修订点 (What Changed)

以下改动用于保证 Verilator 全量/近全量回归可以稳定运行，并与官方回归脚本保持一致：

1.  **工具目录对齐与缓存一致性**
    - 统一工具安装目录：`tools/verilator`、`tools/spike`，与 GitHub Actions 缓存路径一致。
    - 通过环境变量明确 `VERILATOR_INSTALL_DIR`、`SPIKE_INSTALL_DIR`。
2.  **系统依赖与 Python 依赖补齐**
    - 在构建层显式安装 `autoconf`/`bison`/`flex`/`help2man`/`dtc` 等依赖。
    - 安装 `verif/sim/dv/requirements.txt`，确保 `cva6.py` 可执行。
3.  **优先调用官方回归脚本**
    - Verilator/Spike 的安装切换到 `verif/regress/install-*.sh`，减少环境偏差。
4.  **本地路径解析稳定化**
    - 通过脚本位置推导项目根目录，避免从子目录执行时路径错误。
5.  **套件提示补全**
    - `run_test_suite.sh` 的错误提示中包含 `coremark`/`dhrystone` 等可用套件。

## 6. 我对当前 CI 任务的理解 (Understanding)

目标是构建一个以 Verilator 为主的自动化验证流程，尽可能覆盖现有的回归用例，包括：

* **基础冒烟**：快速验证最关键路径是否可跑。
* **架构测试**：RISC-V 官方/衍生测试列表。
* **基准测试**：Coremark、Dhrystone 与其他 benchmark。
* **全量回归**：覆盖更大范围的 testlist，并尽可能接近“官方 CI 的覆盖范围”。

实现策略是：
1. **所有测试入口统一走 `verif/regress/*.sh`**，与官方脚本保持一致。
2. **通过 `run_test_suite.sh` 做“人类友好映射”**，简化 workflow。
3. **工具链/仿真器/依赖安装统一在 `build_infrastructure.sh`**，并与 CI 缓存对齐。

## 7. 新手如何继续这个工作 (Newcomer Guide)

下面按最容易上手的顺序说明如何继续扩展/稳定这个 CI：

### 7.1 本地复现与验证
1. **进入仓库根目录**。
2. **构建基础环境**：
   ```bash
   ./ci/openhw/aws/build_infrastructure.sh
   ```
3. **跑一个最小 smoke**：
   ```bash
   ./ci/openhw/aws/run_test_suite.sh smoke cv32a65x verilator
   ```
4. **跑一个 arch 测试**：
   ```bash
   ./ci/openhw/aws/run_test_suite.sh arch cv64a6_imafdc_sv39 verilator
   ```

### 7.2 扩展测试套件
1. 找到 `verif/regress/` 下要用的脚本。
2. 在 `ci/openhw/aws/run_test_suite.sh` 增加映射（case 分支）。
3. 更新 README_CN，说明新套件用途与范围。

### 7.3 扩展矩阵或目标配置
1. 修改 `.github/workflows/verilator-apu-ci.yml` 的 `matrix`。
2. 注意 **`cv32`/`cv64` 与 testlist 的匹配**，避免跑错架构。
3. 建议先在本地跑一遍，再放到 CI。

### 7.4 排查失败
1. **先看 CI artifacts**：`verif/sim/out_*`。
2. **看 `cva6.py` 生成的日志**（通常在 `out_*/simulate.log`）。
3. **对照 testlist**，确认脚本指向的是正确的 YAML 或测试名。
4. 若是依赖问题，先检查 `build_infrastructure.sh` 是否包含所需包。

### 7.5 常见注意事项
* **不要在这里修改 CVA6 主体 RTL/验证代码**，保持 CI 脚本的独立性。
* **生成文件不要提交**（如 `verif/sim/*.traces`），避免污染仓库。
* **尽量复用官方回归脚本**，减少偏差。

## 8. 调试与拓展指南 (Debug & Extension)

### 如何调试 (Debugging)
如果 CI 报错，建议按以下步骤排查：
1.  **查看 Artifacts**：CI 会将 `verif/sim/out_*/` 目录打包上传。下载并解压，查看具体的日志文件（如 `simulate.log`）。
2.  **本地复现**：
    由于脚本解耦，您可以在本地复现 CI 过程（前提是本地已安装好工具链）：
    ```bash
    # 1. 设置环境 (可选，如果本地已有环境)
    # source ci/openhw/aws/env_setup.sh

    # 2. 运行特定测试
    # ./ci/openhw/aws/run_test_suite.sh <suite> <config> verilator
    # 例如：
    ./ci/openhw/aws/run_test_suite.sh smoke cv32a65x verilator
    ```

### 如何拓展 (Extension)

#### 添加新的测试套件
1.  找到 `verif/regress/` 下的目标脚本。
2.  编辑 `ci/openhw/aws/run_test_suite.sh`。
3.  在 `case "$SUITE_NAME" in` 块中添加新的分支，指定对应的脚本名。

#### 添加新的仿真器 (如 Questa/DSim)
1.  编辑 `ci/openhw/aws/env_setup.sh`：添加该仿真器的环境变量（如 `QUESTASIM_HOME`）。
2.  编辑 `ci/openhw/aws/run_verification.sh`：
    *   在 `# --- Simulator Logic ---` 部分添加逻辑。
    *   设置对应的 `DV_SIMULATORS` 变量（例如 `vcs` 或 `questa`）。
3.  在 CI 配置文件或命令行中调用时，将第三个参数从 `verilator` 改为新的仿真器名。
