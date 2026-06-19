# 常见问题

## 安装阶段

### chromadb 依赖 onnxruntime 报错

**报错信息：** 安装 `chromadb` 时出现 `onnxruntime` 相关错误。

**原因：** `chromadb` 依赖 `onnxruntime` 进行向量计算，但某些系统（特别是较新的 macOS / Linux 发行版）可能缺少合适的预编译包。

**解决：**

```bash
source .venv/bin/activate
pip install --upgrade onnxruntime
```

如果仍有问题，尝试安装指定版本：

```bash
pip install onnxruntime==1.17.1
```

---

### HuggingFace 下载超时

**报错信息：** 首次运行 `index.py` 时模型下载卡住或报网络错误。

**原因：** 中国大陆访问 HuggingFace 官方站点不稳定。

**解决：**

设置镜像环境变量后重新运行：

```bash
export HF_ENDPOINT=https://hf-mirror.com
source .venv/bin/activate
python index.py --full
```

如希望永久生效，将 `export HF_ENDPOINT=https://hf-mirror.com` 写入 `~/.zshrc` 或 `~/.bashrc`。

---

### macOS 缺少 clang 编译器

**报错信息：** 安装依赖时出现 `error: command 'clang' failed` 或 `xcrun: error: invalid active developer path`。

**原因：** macOS Command Line Tools 未安装，某些 Python 包需要编译本地扩展。

**解决：**

```bash
xcode-select --install
```

安装完成后，在弹出的对话框中点击"安装"，等待下载完成，然后重新运行：

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 索引阶段

### 首次索引很慢

**现象：** `index.py --full` 运行了 15-20 分钟还没完成。

**原因：** 这是正常的。首次索引需要：
1. 从 HuggingFace 下载模型文件（~500MB，网络速度决定用时）
2. 遍历所有文章，每篇切块 + 向量化
3. 约 350 篇文章需要处理

后续增量索引（不加 `--full`）只需处理新增或变更的文件，速度快得多。

**建议：** 耐心等待。你可以通过检查 chroma_db 目录大小变化来确认进度：

```bash
du -sh chroma_db   # 看看目录是否在增长
```

---

### 报错 "No module named xxx"

**现象：** 运行索引或搜索时报缺少某个 Python 模块。

**原因：** 未激活虚拟环境，或依赖未完整安装。

**解决：**

```bash
# 激活虚拟环境
source .venv/bin/activate

# 如果还报错，重新安装依赖
pip install -r requirements.txt
```

---

### 磁盘空间不足

**现象：** 索引过程中报磁盘空间不足。

**原因：** `chroma_db` 目录会随着索引文档数量增长而变大。约 350 篇文章的向量数据可能占用数百 MB 到数 GB

**解决：**
- 检查剩余空间：`df -h`
- 清理不必要的文件
- 将 `chroma_db` 迁移到更大磁盘分区的路径
- 在 `config.yaml` 中修改 `persist_directory` 指向新位置

---

## 搜索阶段

### 搜索不到已索引的内容

**问题：** 明明索引了某个文档，但搜索关键词时找不到。

**排查步骤：**

1. **检查文档是否确实已索引：**

```bash
python search.py --stats
```

查看已索引的文档数量。如果数量为 0 或远少于预期，说明索引未完成。

2. **尝试更宽泛的关键词：**

向量搜索基于语义，但如果你的查询太具体，也可能匹配不到。先用文档中明确的词语搜索。

3. **调整块大小：**

如果块太大，特定细节可能被稀释；如果块太小，关键上下文可能丢失。尝试在 `config.yaml` 中调整 `chunk_size` 后重新索引。

4. **检查编码问题：**

确保文档为 UTF-8 编码。GBK 或其他编码可能导致内容被错误解析。

---

### 搜索结果不相关

**问题：** 能搜到内容，但返回的结果与问题无关。

**解决：**

1. **增加 top_k：** 在搜索时指定返回更多结果：

```bash
python search.py "关键词" --top-k 10
```

2. **换一种问法：** 尝试用文档中可能使用的词汇重述问题。

3. **检查切块策略：** 如果文档有明确的 ## 标题，确保使用策略 A（结构感知切块）。

4. **数据质量问题：** 源文档本身可能就模糊或混乱。

---

### 一个块包含多个主题

**问题：** 检索到一个块，但里面混了两三个不同主题的内容。

**原因：** Markdown 中不同标题之间没有空行，导致切块时被合并在了一起。

**解决：** 在源文档的每个 `##` 标题前加一个空行：

```markdown
## 标题一
正文...

（空行）
## 标题二
正文...
```

这会让结构感知切块（策略 A）正确识别标题边界。

---

## MCP 阶段

### Claude Code 不调用搜索工具

**问题：** 在 Claude Code 中提问，但 Claude 没有触发 kb-builder 搜索。

**排查：**

1. **检查 MCP 配置：**

```bash
cat ~/.claude/settings.json | grep -A 5 kb-builder
```

确认配置存在且路径正确。

2. **检查 MCP 状态：**

在 Claude Code 中输入 `/mcp`，查看 `kb-builder` 是否显示并处于连接状态。

3. **重启 Claude Code：**

MCP 配置变更需要重启才能生效。

4. **检查 Python 路径是否正确：**

配置中的 `command` 路径必须指向 `.venv/bin/python` 的**绝对路径**。

---

### 服务器启动报错

**问题：** MCP 服务器无法启动，Claude Code 中 `kb-builder` 状态为红色。

**解决：**

在终端中手动运行服务器查看具体错误：

```bash
cd /path/to/kb-builder
source .venv/bin/activate
python -m mcp.kb_server
```

常见错误及解决：

| 错误 | 原因 | 解决 |
|------|------|------|
| `ModuleNotFoundError` | 依赖未安装 | `pip install -r requirements.txt` |
| `No such file or directory` | Python 路径不对 | 检查 settings.json 中的路径 |
| Connection refused | 端口被占用 | 检查是否有其他进程占用端口 |
