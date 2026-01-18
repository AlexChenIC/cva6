#!/bin/bash
# CVA6 本地 CI 环境配置脚本
# 用途：一键设置本地开发和测试环境
# 作者：OpenHW CI Team
# 日期：2026-01-17

set -e  # 遇到错误立即退出

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印函数
info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查是否在 CVA6 根目录
check_cva6_root() {
    if [ ! -f "Makefile" ] || [ ! -d "verif" ] || [ ! -d "core" ]; then
        error "请在 CVA6 根目录运行此脚本"
        error "当前目录: $(pwd)"
        exit 1
    fi
    export CVA6_ROOT=$(pwd)
    success "CVA6 根目录: $CVA6_ROOT"
}

# 检查并设置 RISCV 工具链
setup_riscv_toolchain() {
    info "检查 RISC-V 工具链..."

    if [ -z "$RISCV" ]; then
        warning "RISCV 环境变量未设置"

        # 尝试使用本地工具链
        if [ -d "$CVA6_ROOT/tools/riscv-toolchain" ]; then
            export RISCV=$CVA6_ROOT/tools/riscv-toolchain
            info "使用本地工具链: $RISCV"
        else
            error "RISCV 工具链未找到"
            echo ""
            echo "请设置 RISCV 环境变量或运行以下命令安装："
            echo "  source ci/install-prereq.sh"
            echo "  bash ci/install-toolchain.sh"
            echo ""
            echo "或手动设置："
            echo "  export RISCV=/path/to/riscv-toolchain"
            exit 1
        fi
    fi

    # 验证工具链
    if [ ! -x "$RISCV/bin/riscv64-unknown-elf-gcc" ] && [ ! -x "$RISCV/bin/riscv32-unknown-elf-gcc" ]; then
        error "RISCV 工具链无效: $RISCV"
        error "未找到 riscv64-unknown-elf-gcc 或 riscv32-unknown-elf-gcc"
        exit 1
    fi

    success "RISCV 工具链: $RISCV"

    # 设置相关变量
    export LIBRARY_PATH="$RISCV/lib"
    export LD_LIBRARY_PATH="$RISCV/lib:${LD_LIBRARY_PATH:-}"
    export C_INCLUDE_PATH="$RISCV/include"
    export CPLUS_INCLUDE_PATH="$RISCV/include"

    # 自动检测前缀
    if [ -z "$CV_SW_PREFIX" ]; then
        export CV_SW_PREFIX=$(ls -1 $RISCV/bin/riscv* | head -n 1 | rev | cut -d '/' -f 1 | cut -d '-' -f 2- | rev)-
        info "工具链前缀: $CV_SW_PREFIX"
    fi
}

# 检查并设置并行编译数
setup_num_jobs() {
    if [ -z "$NUM_JOBS" ]; then
        # 自动检测 CPU 核心数
        if command -v nproc &> /dev/null; then
            NUM_CORES=$(nproc)
        elif command -v sysctl &> /dev/null; then
            NUM_CORES=$(sysctl -n hw.ncpu)
        else
            NUM_CORES=4
        fi

        # 使用 2/3 的核心数
        export NUM_JOBS=$(( NUM_CORES * 2 / 3 ))
        if [ $NUM_JOBS -lt 1 ]; then
            export NUM_JOBS=1
        fi
    fi
    info "并行编译数: NUM_JOBS=$NUM_JOBS"
}

# 检查 Verilator
check_verilator() {
    info "检查 Verilator..."

    local verilator_path="$CVA6_ROOT/tools/verilator/bin/verilator"

    if [ -x "$verilator_path" ]; then
        export VERILATOR_INSTALL_DIR=$CVA6_ROOT/tools/verilator
        export PATH="$VERILATOR_INSTALL_DIR/bin:$PATH"
        local version=$($verilator_path --version 2>&1 | head -n 1)
        success "Verilator: $version"
        success "路径: $VERILATOR_INSTALL_DIR"
    elif command -v verilator &> /dev/null; then
        local version=$(verilator --version 2>&1 | head -n 1)
        warning "使用系统 Verilator: $version"
        warning "推荐使用 CVA6 指定版本（v5.008）"
        echo "  运行安装命令: bash verif/regress/install-verilator.sh"
    else
        error "Verilator 未找到"
        echo ""
        echo "请运行以下命令安装："
        echo "  bash verif/regress/install-verilator.sh"
        echo ""
        echo "预计安装时间: ~15 分钟（NUM_JOBS=$NUM_JOBS）"
        return 1
    fi
}

# 检查 Spike
check_spike() {
    info "检查 Spike ISS..."

    local spike_path="$CVA6_ROOT/tools/spike/bin/spike"

    if [ -x "$spike_path" ]; then
        export SPIKE_INSTALL_DIR=$CVA6_ROOT/tools/spike
        export SPIKE_PATH="$SPIKE_INSTALL_DIR/bin"
        export PATH="$SPIKE_PATH:$PATH"

        # 设置 SPIKE_SRC_DIR（cva6.py 需要）
        export SPIKE_SRC_DIR="$CVA6_ROOT/verif/core-v-verif/vendor/riscv/riscv-isa-sim"

        success "Spike: $SPIKE_INSTALL_DIR"
        info "SPIKE_SRC_DIR: $SPIKE_SRC_DIR"
    else
        error "Spike 未找到"
        echo ""
        echo "请运行以下命令安装："
        echo "  bash verif/regress/install-spike.sh"
        echo ""
        echo "预计安装时间: ~5 分钟"
        return 1
    fi
}

# 检查测试套件
check_test_suites() {
    info "检查测试套件..."

    local all_ok=true

    # riscv-tests
    if [ -d "$CVA6_ROOT/tmp/riscv-tests" ]; then
        success "riscv-tests: 已安装"
    else
        warning "riscv-tests: 未安装"
        echo "  运行: bash verif/regress/install-riscv-tests.sh"
        all_ok=false
    fi

    # riscv-arch-test
    if [ -d "$CVA6_ROOT/tmp/riscv-arch-test" ]; then
        success "riscv-arch-test: 已安装"
    else
        warning "riscv-arch-test: 未安装"
        echo "  运行: bash verif/regress/install-riscv-arch-test.sh"
        all_ok=false
    fi

    if [ "$all_ok" = false ]; then
        warning "部分测试套件未安装，首次运行测试时会自动安装"
    fi
}

# 加载 CVA6 环境配置
load_cva6_env() {
    info "加载 CVA6 环境配置..."

    # 设置项目路径
    export ROOT_PROJECT=$CVA6_ROOT
    export RTL_PATH="$ROOT_PROJECT/"
    export TB_PATH="$ROOT_PROJECT/verif/tb/core"
    export TESTS_PATH="$ROOT_PROJECT/verif/tests"

    # RISCV-DV 路径
    export RISCV_DV_ROOT="$ROOT_PROJECT/verif/sim/dv"
    export CVA6_DV_ROOT="$ROOT_PROJECT/verif/env/corev-dv"

    # 更新 PATH
    export PATH="$VERILATOR_INSTALL_DIR/bin:$RISCV/bin:$SPIKE_PATH:$PATH"

    success "环境配置加载完成"
}

# 显示环境摘要
show_summary() {
    echo ""
    echo "======================================"
    echo "  CVA6 环境配置摘要"
    echo "======================================"
    echo ""
    echo "CVA6 根目录:      $CVA6_ROOT"
    echo "RISCV 工具链:     $RISCV"
    echo "工具链前缀:       $CV_SW_PREFIX"
    echo "并行编译数:       NUM_JOBS=$NUM_JOBS"
    echo ""
    echo "Verilator:        ${VERILATOR_INSTALL_DIR:-未设置}"
    echo "Spike:            ${SPIKE_INSTALL_DIR:-未设置}"
    echo ""
    echo "======================================"
    echo ""
}

# 运行快速验证测试
run_quick_test() {
    echo ""
    read -p "是否运行快速验证测试？(约 5 分钟) [y/N]: " -n 1 -r
    echo

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        info "运行快速测试..."
        echo ""

        cd $CVA6_ROOT/verif/sim

        # 运行单个测试
        DV_SIMULATORS=veri-testharness,spike \
        DV_TARGET=cv64a6_imafdc_sv39 \
        python3 cva6.py \
            --target cv64a6_imafdc_sv39 \
            --iss veri-testharness,spike \
            --iss_yaml cva6.yaml \
            --test rv64ui-p-add

        if [ $? -eq 0 ]; then
            echo ""
            success "快速测试通过！环境配置正确。"
        else
            echo ""
            error "快速测试失败，请检查环境配置"
            error "查看日志: $CVA6_ROOT/verif/sim/logfile.log"
            return 1
        fi
    else
        info "跳过快速测试"
        echo ""
        echo "手动运行测试："
        echo "  cd verif/sim"
        echo "  DV_SIMULATORS=veri-testharness,spike \\"
        echo "  DV_TARGET=cv64a6_imafdc_sv39 \\"
        echo "  python3 cva6.py --test rv64ui-p-add"
    fi
}

# 保存环境变量到文件
save_env() {
    local env_file="$CVA6_ROOT/.cva6_env"

    cat > $env_file << EOF
# CVA6 环境配置
# 自动生成于: $(date)
# 使用方法: source .cva6_env

export CVA6_ROOT=$CVA6_ROOT
export RISCV=$RISCV
export NUM_JOBS=$NUM_JOBS
export CV_SW_PREFIX=$CV_SW_PREFIX

export VERILATOR_INSTALL_DIR=$VERILATOR_INSTALL_DIR
export SPIKE_INSTALL_DIR=$SPIKE_INSTALL_DIR
export SPIKE_PATH=$SPIKE_PATH
export SPIKE_SRC_DIR=$SPIKE_SRC_DIR

export ROOT_PROJECT=$ROOT_PROJECT
export RTL_PATH=$RTL_PATH
export TB_PATH=$TB_PATH
export TESTS_PATH=$TESTS_PATH
export RISCV_DV_ROOT=$RISCV_DV_ROOT
export CVA6_DV_ROOT=$CVA6_DV_ROOT

export LIBRARY_PATH=$LIBRARY_PATH
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH
export C_INCLUDE_PATH=$C_INCLUDE_PATH
export CPLUS_INCLUDE_PATH=$CPLUS_INCLUDE_PATH

export PATH=$PATH
EOF

    success "环境配置已保存到: $env_file"
    echo ""
    echo "下次可以直接加载："
    echo "  source .cva6_env"
}

# 主函数
main() {
    echo ""
    echo "======================================"
    echo "  CVA6 本地环境配置向导"
    echo "======================================"
    echo ""

    check_cva6_root
    setup_riscv_toolchain
    setup_num_jobs

    # 检查工具（允许失败）
    check_verilator || true
    check_spike || true
    check_test_suites

    load_cva6_env
    show_summary
    save_env

    # 可选：运行快速测试
    if [ -x "$VERILATOR_INSTALL_DIR/bin/verilator" ] && [ -x "$SPIKE_INSTALL_DIR/bin/spike" ]; then
        run_quick_test || true
    else
        warning "Verilator 或 Spike 未安装，跳过快速测试"
        echo ""
        echo "请先安装必要工具："
        echo "  bash verif/regress/install-verilator.sh"
        echo "  bash verif/regress/install-spike.sh"
    fi

    echo ""
    success "环境配置完成！"
    echo ""
    echo "下一步："
    echo "  1. 运行 smoke test:"
    echo "     cd verif/sim"
    echo "     DV_SIMULATORS=veri-testharness,spike DV_TARGET=cv64a6_imafdc_sv39 \\"
    echo "     bash ../regress/smoke-tests-cv64a6_imafdc_sv39.sh"
    echo ""
    echo "  2. 阅读文档:"
    echo "     docs/ci/01_ci_for_beginners.md"
    echo "     docs/ci/02_current_cva6_ci_inventory.md"
    echo ""
}

# 运行主函数
main "$@"
