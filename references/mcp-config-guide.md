# MCP 配置指南

## 什么是 MCP

MCP（Model Context Protocol）是 Claude Code 与外部工具通信的标准协议。通过 MCP，Claude Code 可以调用 kb-builder 的知识库搜索功能，在对话中实时检索文档。

简单来说：安装后你可以在 Claude Code 中直接问"搜索知识库关于部署的内容"，Claude 会自动调用 kb-builder 工具来查找答案。

---

## 自动配置（install.sh）

`install.sh` 会自动完成 MCP 配置，主要做三件事：

1. 创建 Python 虚拟环境（.venv）并安装依赖
2. 首次下载向量化模型（~500MB）
3. 在 `~/.claude/settings.json` 中添加 kb-builder 的 MCP 服务器配置

### 配置内容

```json
{
  "mcpServers": {
    "kb-builder": {
      "command": "/Users/magebte/Documents/GitHub/kb-builder/.venv/bin/python",
      "args": [
        "-m",
        "mcp.kb_server"
      ],
      "env": {}
    }
  }
}
```

`install.sh` 会自动将路径替换为你的实际仓库路径。

---

## 手动配置

如果自动配置失败，或你需要在其他机器上手动配置：

### 第一步：找到你的 Python 路径

```bash
cd /path/to/kb-builder
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
which python
```

### 第二步：编辑 Claude Code 设置

打开 `~/.claude/settings.json`（如不存在则创建），添加或合并：

```json
{
  "mcpServers": {
    "kb-builder": {
      "command": "/完整路径/kb-builder/.venv/bin/python",
      "args": ["-m", "mcp.kb_server"],
      "env": {}
    }
  }
}
```

> 如果你在 `~/.claude/settings.json` 中已经定义了其他 MCP 服务器，只需在 `mcpServers` 对象中添加 `kb-builder` 条目即可，不要删除其他配置。

### 第三步：重启 Claude Code

关闭当前 Claude Code 会话，重新启动。新配置在重启后生效。

---

## 验证 MCP 是否工作

### 方法一：问 Claude

在 Claude Code 中输入：

```
搜索知识库关于 xxx 的内容
```

或

```
/知识库 xxx
```

如果 MCP 配置正确，Claude 会主动调用 kb-builder 工具并返回检索结果。

### 方法二：检查 MCP 状态

在 Claude Code 中输入：

```
/mcp
```

查看列表中是否有 `kb-builder` 条目，且状态为绿色（已连接）。

### 方法三：手动测试服务器

在终端中运行：

```bash
source /path/to/kb-builder/.venv/bin/activate
python -m mcp.kb_server
```

如果没有报错，说明服务器启动正常。按 `Ctrl+C` 退出。

---

## 卸载

如果不再需要 kb-builder 的 MCP 功能：

### 第一步：移除 MCP 配置

编辑 `~/.claude/settings.json`，删除 `mcpServers` 中的 `kb-builder` 条目：

```json
// 删除这一整段
"kb-builder": {
  "command": "...",
  "args": [...],
  "env": {}
}
```

### 第二步：重启 Claude Code

关闭并重新打开 Claude Code，使配置变更生效。

### 第三步：（可选）删除虚拟环境

```bash
cd /path/to/kb-builder
rm -rf .venv
```

如需完全清理，还可删除 ChromaDB 存储目录（重新索引时会重新创建）：

```bash
rm -rf chroma_db  # 位于 kb-builder 目录下
```
