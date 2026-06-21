# KB Builder

一键构建 AI 知识库的 Claude Code Skill。支持从 Web UI 动态接入 Git 仓库、在线文档站、RSS feed 等多种知识库来源。

## 简介

KB Builder 将你的 Markdown 文档自动索引到向量数据库中，通过 MCP（Model Context Protocol）提供语义搜索能力。

- **CLI 检索**：命令行快速验证检索质量
- **MCP 接入**：在 Claude Code 中直接语义搜索你的知识库
- **Web UI**：浏览器图形化搜索 + 动态管理知识库来源

## 快速开始（3 步）

### 第 1 步：安装

```bash
git clone https://github.com/MageByte-Zero/kb-builder.git
cd kb-builder
bash scripts/install.sh
```

安装脚本会自动：创建虚拟环境 → 安装依赖 → 可选克隆示例知识库 → 注册 MCP → 首次索引。

### 第 2 步：启动 Web UI

```bash
# 激活虚拟环境
source .venv/bin/activate

# 启动服务
python web.py
```

浏览器打开 **http://127.0.0.1:8000** 即可使用。

### 第 3 步：搜索

- 在搜索框输入关键词，回车或点击「搜索」
- 点击左侧推荐标签快速搜索
- 点击结果卡片查看文章全文

## 动态接入知识库

在 Web UI 左侧边栏底部，点击「管理来源」即可添加新的知识库：

| 类型 | 输入示例 | 说明 |
|------|----------|------|
| Git 仓库 | `https://github.com/user/repo.git` | 自动 clone 并索引所有 .md 文件 |
| 在线文档 | `https://docs.example.com` | 抓取页面内容转 Markdown 后索引 |
| RSS/Atom | `https://blog.example.com/feed.xml` | 拉取 feed 条目索引 |

添加后系统自动在后台完成：拉取内容 → 分块 → 向量化 → 入库，状态实时更新。

## 日常使用

```bash
# 激活环境
source .venv/bin/activate

# 启动 Web UI
python web.py

# 同步内容源最新内容（如 awesome-ai-kb 有更新）
cd ~/awesome-ai-kb && git pull
cd ~/Documents/GitHub/kb-builder/scripts && python index.py index

# CLI 快速检索（不用开浏览器）
cd scripts && python search.py "你的问题"

# 查看索引状态
cd scripts && python index.py stats

# 查看主题分布
cd scripts && python index.py topics
```

## 前置依赖

- **Python 3.10+**
- **Git**
- **Claude Code**（MCP 功能需要）

## 配置说明

编辑 `scripts/config.yaml` 声明静态内容源：

```yaml
content_sources:
  - path: ~/awesome-ai-kb
    name: magebyte-ai-kb
    enabled: true
```

通过 Web UI 动态添加的来源保存在 `scripts/sources.json`，两者启动时自动合并。

## 目录结构

```
kb-builder/
├── scripts/
│   ├── sources/            # 来源管理（Manager + Adapters）
│   │   ├── manager.py      # SourceManager: CRUD + JSON 持久化
│   │   └── adapters.py     # GitAdapter, DocsAdapter, RssAdapter
│   ├── config.yaml         # 静态内容源配置
│   ├── index.py            # 索引管道（分块 → embedding → ChromaDB）
│   ├── search.py           # CLI 检索工具
│   └── install.sh          # 一键安装脚本
├── mcp/
│   └── kb_server.py        # MCP Server（Claude Code 接入）
├── web/
│   ├── app.py              # FastAPI 后端
│   ├── templates/
│   │   └── index.html      # 前端页面
│   └── static/
│       ├── style.css       # 样式
│       └── app.js          # 前端逻辑
├── web.py                  # Web UI 启动入口
├── references/             # 参考文档
└── templates/              # 内容仓库模板
```

## 常见问题

**Q: 首次索引很慢？**
A: 首次需要下载 embedding 模型（~500MB），后续会缓存。可设置 `HF_ENDPOINT=https://hf-mirror.com` 使用国内镜像加速。

**Q: 搜索结果不相关？**
A: 尝试调整 `config.yaml` 中的 `chunking.article_max_size`（默认 800），或用 `python search.py "问题" --top-k 10` 看更多结果。

**Q: Web UI 端口被占用？**
A: `python web.py --port 8080` 换个端口。
