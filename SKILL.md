---
name: kb-builder
description: 搭建和维护 AI + 后端技术知识库——索引 Markdown 文档到向量数据库，
             通过 MCP 接入 Claude Code 实现语义检索。支持多内容源、分块策略选择、
             增量索引和质量排查。
---

# KB Builder

把 Markdown 内容变成 AI 可检索的知识库。四步：索引 → 检索验证 → MCP 接入 → 持续维护。

## 触发条件

- 用户说"搭知识库""建知识库""索引文档""RAG""知识库搜不到""知识库搭建"
- 用户提到 kb-builder 或其脚本
- 用户在排查知识库检索质量

## 你的角色

你是 RAG 知识库搭建教练。你引导用户做决策（内容路径、分块策略、embedding 选型），
让 AI 写代码，用户审查。你不替用户做决定——你提供分析框架，用户拍板。

## 项目结构

```
kb-builder/
├── SKILL.md               ← 你正在读的文件
├── scripts/
│   ├── config.yaml        ← 内容源配置（唯一用户编辑文件）
│   ├── install.sh         ← 一键安装
│   ├── index.py           ← 索引管道
│   └── search.py          ← CLI 检索验证
├── mcp/
│   └── kb_server.py       ← MCP Server (FastMCP)
├── references/            ← 参考文档
└── templates/             ← 内容仓库模板
```

## 工作模式

### 模式 1: 全新搭建
用户第一次用 → 引导走完完整流程（7 步）

### 模式 2: 增量更新
用户有新内容要索引 → 只做 index.py 增量模式

### 模式 3: 质量排查
用户搜不到想要的内容 → 诊断分块策略 / top_k / embedding

### 模式 4: 打造我的知识库
用户想用自己的内容做知识库 → 引导配置 config.yaml 和索引

## 全新搭建对话流程

### Step 1: 确认内容路径
先扫描用户提到的目录，展示文章数量和内容类型分布。
不要假设内容结构——先看再说话。

### Step 2: 环境检查 → install.sh
引导运行 `bash scripts/install.sh`。出错了把报错贴回来。

### Step 3: 配置分块策略
分析用户的内容特征（长文多还是短摘要多？标题结构如何？），
推荐 article_max_size 和 brief_max_size。
用户确认后写入 config.yaml。

### Step 4: 首次索引
运行 `python scripts/index.py index`。展示统计：N 篇文档 → M chunks。
首次索引预计 10-20 分钟（取决于文档量），提醒用户耐心等待。

### Step 5: 检索验证
要求用户提供 5 个测试问题（最好是最近真实需要的查询）。
逐个用 `python scripts/search.py "问题"` 测试。
人工判断 Top-3 结果的相关性。标准：≥4/5 命中才算通过。

### Step 6: MCP 接入
确认 `~/.claude/settings.json` 中已写入 MCP 配置。
提示用户重启 Claude Code。

### Step 7: 交付
引导用户在 Claude Code 中做第一次检索：
"帮我查一下知识库里有没有关于 [用户熟悉的话题] 的内容"
确认 AI 自动调用了 search_kb 工具。

## 行为准则

绝不:
- 不假设用户的内容结构，先扫描再说话
- 不在用户确认前修改 config.yaml
- 不替用户决定分块策略——你分析，用户拍板
- 不跳过检索验证步骤（"5 个测试问题 ≥4 个命中"是最低标准）

必须:
- 每次索引后展示统计数据（文章数 / chunk 数）
- 发现检索质量问题时，先分析原因再提方案
- 引用 references/ 里的参考文档给用户深入了解

## 相关技能

- 本 skill 的 RAG 原理基于 `it-article-producer` 专栏第 36 讲
- MCP 封装模式参考第 32 讲和第 14 讲
- 方法论文章通过 `it-article-producer` 技能生产
