#!/bin/bash
# KB Builder — 一键安装脚本
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo ""
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  KB Builder — AI 知识库安装脚本${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

# ── 1. 环境检查 ──────────────────────────────────────────
echo -e "${CYAN}[1/6]${NC} 检查环境..."

check_cmd() {
    if ! command -v "$1" &> /dev/null; then
        echo -e "  ${RED}✗${NC} 未找到 $1，请先安装"
        MISSING_DEPS=1
    else
        local ver=$("$1" --version 2>&1 | head -1)
        echo -e "  ${GREEN}✓${NC} $1 — ${ver:0:60}"
    fi
}

MISSING_DEPS=0
check_cmd python3
check_cmd pip3
check_cmd git

if [[ "$MISSING_DEPS" == "1" ]]; then
    echo ""
    echo -e "${RED}[ERROR]${NC} 缺少必要依赖，请安装后重试。"
    exit 1
fi

# Python 版本检查
PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo -e "  ${GREEN}✓${NC} Python $PY_VER"
echo ""

# ── 2. 安装依赖 ──────────────────────────────────────────
echo -e "${CYAN}[2/6]${NC} 安装 Python 依赖..."

# 创建 venv（避免污染全局环境）
if [[ ! -d "$SKILL_DIR/.venv" ]]; then
    echo "  创建虚拟环境..."
    python3 -m venv "$SKILL_DIR/.venv"
fi

source "$SKILL_DIR/.venv/bin/activate"
echo -e "  ${GREEN}✓${NC} 虚拟环境已激活"

pip install --quiet --upgrade pip 2>/dev/null

echo "  安装 chromadb fastmcp sentence-transformers pyyaml ..."
pip install --quiet chromadb "fastmcp>=2.0" sentence-transformers pyyaml mcp

echo -e "  ${GREEN}✓${NC} 依赖安装完成"
echo ""

# ── 3. 交互配置 ──────────────────────────────────────────
echo -e "${CYAN}[3/6]${NC} 配置内容源..."
echo ""

CLONE_KB="n"
OWN_PATH=""

read -p "  是否克隆码哥的公开知识库内容 (awesome-ai-kb)? [Y/n]: " CLONE_KB
CLONE_KB=${CLONE_KB:-y}

if [[ "$CLONE_KB" =~ ^[Yy]$ ]]; then
    KB_DIR="$HOME/awesome-ai-kb"
    if [[ -d "$KB_DIR" ]]; then
        echo -e "  ${YELLOW}⚠${NC}  $KB_DIR 已存在，跳过克隆"
        echo "    如需更新内容: cd $KB_DIR && git pull"
    else
        echo "  正在克隆 https://github.com/MageByte-Zero/awesome-ai-kb.git ..."
        if git clone https://github.com/MageByte-Zero/awesome-ai-kb.git "$KB_DIR" 2>/dev/null; then
            echo -e "  ${GREEN}✓${NC} 内容已克隆到 $KB_DIR"
        else
            echo -e "  ${YELLOW}⚠${NC}  克隆失败（仓库可能尚未公开）。"
            echo "    你可以稍后手动克隆，或跳过此步先索引自己的内容。"
            CLONE_KB="n"
        fi
    fi
fi

echo ""
read -p "  你有自己的内容目录吗？输入路径（留空跳过）: " OWN_PATH

# ── 4. 写 config.yaml ─────────────────────────────────────
echo ""
echo -e "${CYAN}[4/6]${NC} 生成 config.yaml..."

CONFIG_FILE="$SCRIPT_DIR/config.yaml"

if [[ "$CLONE_KB" =~ ^[Yy]$ ]]; then
    ENABLED_KB="true"
else
    ENABLED_KB="false"
fi

cat > "$CONFIG_FILE" << EOF
# KB Builder 配置文件
# 编辑此文件声明你的内容源

content_sources:
  - path: $HOME/awesome-ai-kb
    name: magebyte-ai-kb
    enabled: $ENABLED_KB
EOF

if [[ -n "$OWN_PATH" ]]; then
    OWN_PATH_EXPANDED=$(eval echo "$OWN_PATH" 2>/dev/null || echo "$OWN_PATH")
    cat >> "$CONFIG_FILE" << EOF
  - path: $OWN_PATH_EXPANDED
    name: my-kb
    enabled: true
EOF
else
    cat >> "$CONFIG_FILE" << EOF
  # - path: ~/my-content
  #   name: my-kb
  #   enabled: false
EOF
fi

cat >> "$CONFIG_FILE" << 'EOF'

index:
  collection_name: unified_kb
  persist_dir: ./chroma_db
  embedding_model: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
  # embedding_model: openai/text-embedding-3-small  # 备选（v2.0 支持），需设置 OPENAI_API_KEY
  device: cpu

chunking:
  article_max_size: 800
  brief_max_size: 600
  # chunk_overlap: 80  # TODO: v2.0 滑动窗口重叠，暂未启用

mcp:
  default_top_k: 5
  max_top_k: 15
EOF

echo -e "  ${GREEN}✓${NC} config.yaml 已生成 → $CONFIG_FILE"

# ── 5. 首次索引 ──────────────────────────────────────────
echo ""
echo -e "${CYAN}[5/6]${NC} 首次索引..."

cd "$SCRIPT_DIR"

if [[ "$ENABLED_KB" == "false" ]] && [[ -z "$OWN_PATH" ]]; then
    echo -e "  ${YELLOW}⚠${NC}  没有启用的内容源，跳过索引。"
    echo "    请编辑 config.yaml 添加内容源后运行:"
    echo "    cd $SCRIPT_DIR && python index.py index"
else
    if python3 index.py index; then
        echo -e "  ${GREEN}✓${NC} 索引完成"
    else
        echo -e "  ${YELLOW}⚠${NC}  索引遇到问题。你可以稍后手动运行:"
        echo "    cd $SCRIPT_DIR && python index.py index"
    fi
fi

# ── 6. MCP 配置注入 ──────────────────────────────────────
echo ""
echo -e "${CYAN}[6/6]${NC} 配置 Claude Code MCP..."

SERVER_PATH="$SKILL_DIR/mcp/kb_server.py"
VENV_PYTHON="$SKILL_DIR/.venv/bin/python3"
CONFIG_PATH="$SCRIPT_DIR/config.yaml"

# 先移除旧的（如果存在）
claude mcp remove ai-knowledge-base -s local 2>/dev/null || true

# 用 claude mcp add 注册（Claude Code 2.x 标准方式）
claude mcp add ai-knowledge-base \
  -e "KB_CONFIG_PATH=$CONFIG_PATH" \
  -e "HF_ENDPOINT=https://hf-mirror.com" \
  -s local \
  -- "$VENV_PYTHON" "$SERVER_PATH" 2>&1

echo -e "  ${GREEN}✓${NC} MCP server 已注册（下次启动 Claude Code 生效）"

# ── 完成 ──────────────────────────────────────────────────
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  安装完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "下一步:"
echo "  1. 重启 Claude Code"
echo "  2. 在 Claude Code 中试试:"
echo "     '帮我查一下知识库里有没有关于 Redis 的文章'"
echo ""
echo "日常维护:"
echo "  # 同步码哥最新内容"
echo "  cd ~/awesome-ai-kb && git pull"
echo ""
echo "  # 增量更新索引"
echo "  cd $SCRIPT_DIR && source ../.venv/bin/activate && python index.py index"
echo ""
echo "  # CLI 快速检索"
echo "  cd $SCRIPT_DIR && source ../.venv/bin/activate && python search.py '你的问题'"
echo ""
