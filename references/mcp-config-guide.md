# MCP 配置指南

## 什么是 MCP

MCP（Model Context Protocol）是 Claude Code 与外部工具通信的标准协议。通过 MCP，Claude Code 可以调用 kb-builder 的知识库搜索功能，在对话中实时检索文档。

简单来说：安装后你可以在 Claude Code 中直接问"帮我查一下知识库里有没有关于 Redis 集群的文章"，Claude 会自动调用知识库工具来查找。

---

## 自动配置（install.sh）

`install.sh` 会自动完成 MCP 配置，主要做三件事：

1. 创建 Python 虚拟环境（`.venv`）并安装依赖
2. 首次索引（下载 embedding 模型 ~500MB + 建立向量库）
3. 通过 `claude mcp add` 命令注册 MCP 服务器

### 自动执行的命令

`install.sh` 会自动执行：

```bash
claude mcp add ai-knowledge-base \
  -e "KB_CONFIG_PATH=/path/to/kb-builder/scripts/config.yaml" \
  -e "HF_ENDPOINT=https://hf-mirror.com" \
  -s local \
  -- /path/to/kb-builder/.venv/bin/python3 /path/to/kb-builder/mcp/kb_server.py
```

路径会自动替换为你的实际安装路径。注册后重启 Claude Code 生效。

---

## 手动配置

如果需要手动配置（比如在其他机器上、或自动配置失败）：

### 第一步：创建虚拟环境并安装依赖

```bash
cd /path/to/kb-builder
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 第二步：注册 MCP 服务器

使用 `claude mcp add` 命令（Claude Code 2.x 标准方式）：

```bash
claude mcp add ai-knowledge-base \
  -e "KB_CONFIG_PATH=/完整路径/kb-builder/scripts/config.yaml" \
  -e "HF_ENDPOINT=https://hf-mirror.com" \
  -s local \
  -- /完整路径/kb-builder/.venv/bin/python3 /完整路径/kb-builder/mcp/kb_server.py
```

> **注意**：必须使用 `.venv/bin/python3`（虚拟环境中的 Python），而不是系统的 `python3`。所有依赖（chromadb、fastmcp 等）都安装在虚拟环境中。
>
> `-s local` 表示注册为本地项目配置（仅当前项目可见）。如需全局生效，改为 `-s user`。
>
> `HF_ENDPOINT=https://hf-mirror.com` 用于加速 HuggingFace 模型下载（国内环境）。

### 第三步：重启 Claude Code

关闭当前 Claude Code 会话，重新启动。新配置在重启后生效。

---

## 验证 MCP 是否工作

### 方法一：在 Claude Code 中检索

重启 Claude Code 后，输入：

```
帮我查一下知识库里有没有关于 Redis 集群的文章
```

如果 MCP 配置正确，Claude 会自动调用 `search_kb` 工具并返回检索结果。

### 方法二：查看索引状态

```
帮我查看知识库的索引状态
```

Claude 应调用 `get_kb_stats` 并返回向量数、内容源等信息。

### 方法三：检查 MCP 连接

在终端中运行 `claude mcp list`，查看 `ai-knowledge-base` 是否显示 ✔ Connected。

### 方法四：手动测试服务器

在终端中测试服务器能否启动：

```bash
/path/to/kb-builder/.venv/bin/python3 /path/to/kb-builder/mcp/kb_server.py
```

如果没有报错（stdio 模式下等待输入是正常的），按 `Ctrl+C` 退出。

---

## 卸载

如果不再需要知识库的 MCP 功能：

### 第一步：移除 MCP 配置

运行 `claude mcp remove ai-knowledge-base -s local`（或 `-s user`，取决于注册时的 scope）。

### 第二步：重启 Claude Code

关闭并重新打开 Claude Code，使配置变更生效。

### 第三步：（可选）清理文件

```bash
rm -rf /path/to/kb-builder/.venv           # 虚拟环境（~500MB）
rm -rf /path/to/kb-builder/scripts/chroma_db  # 向量库（~100MB+）
```
