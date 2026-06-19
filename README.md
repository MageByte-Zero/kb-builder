# KB Builder

一键构建 AI 知识库的 Claude Code Skill。

## 简介

KB Builder 是一个 Claude Code Skill，用于将你的 Markdown 文档自动索引到向量数据库中，并通过 MCP（Model Context Protocol）提供语义搜索能力。

你可以将任意本地 Markdown 文档目录注册为内容源，构建统一的知识库。在 Claude Code 中直接提问，即可从你的私人知识库中检索相关内容。

## 快速开始

```bash
# 1. 克隆仓库
git clone https://github.com/MageByte-Zero/kb-builder.git
cd kb-builder/scripts

# 2. 执行安装脚本
bash install.sh
```

## 前置依赖

- **Python 3.10+** — 向量索引引擎运行环境
- **Git** — 用于克隆内容源仓库
- **Claude Code** — Claude Code CLI 工具 (`npm install -g @anthropic-ai/claude-code`)

## install.sh 做了什么

安装脚本会依次执行以下操作：

1. **环境检查** — 确认 Python、Git、Claude Code 均已安装
2. **安装 Python 依赖** — 自动创建虚拟环境并安装 sentence-transformers、chromadb 等必要库
3. **可选：克隆内容源** — 询问是否要克隆 码哥字节 的公开 AI 知识库 (`awesome-ai-kb`)
4. **配置 MCP** — 将 kb-builder 注册为 Claude Code 的 MCP 工具，使其在对话中可用
5. **初次索引** — 扫描已配置的内容源，构建向量索引

## 使用方法

安装完成后，重启 Claude Code，即可通过自然语言提问：

- "我知识库里有没有关于 Redis Cluster 的内容？"
- "查询 KB 中关于 RAG 架构的资料"
- "从我的知识库中找一下 System Design 相关的文章"

内部通过 MCP 的 `kb_search` 工具实现语义检索，默认返回 Top-5 最相关结果。

## 配置说明

编辑 `scripts/config.yaml` 声明你的内容源：

```yaml
content_sources:
  - path: ~/awesome-ai-kb
    name: magebyte-ai-kb
    enabled: true
```

支持同时注册多个内容源，每个源可以是本地目录或 Git 仓库路径。详细信息请参考 `scripts/config.yaml` 中的注释。

## 目录结构

```
kb-builder/
├── scripts/           # 索引脚本和配置
│   ├── config.yaml    # 用户配置文件（内容源声明）
│   └── install.sh     # 安装脚本
├── mcp/               # MCP 服务器代码
├── references/        # 参考文档
└── templates/         # 内容模板
    └── kb-content-starter/
        ├── articles/
        └── briefs/
```
