# 向量化模型指南

## 向量化模型的作用

RAG 系统需要将文本转换为数值向量（embedding），才能进行语义相似度计算。向量化模型的好坏直接影响检索质量。

kb-builder 默认使用本地模型，不依赖外部 API，开箱即用。

---

## 默认模型：paraphrase-multilingual-MiniLM-L12-v2

| 属性 | 说明 |
|------|------|
| 模型 | paraphrase-multilingual-MiniLM-L12-v2 |
| 类型 | 本地运行，无需 API Key |
| 向量维度 | 384 |
| 支持语言 | 50+ 语言（含中英文），多语言语义对齐 |
| 首次下载 | ~420MB（自动下载到 HuggingFace 缓存目录） |
| 后续使用 | 完全离线，无网络依赖 |

该模型由 sentence-transformers 官方维护，在中文技术文档检索场景表现稳定。384 维向量在保证检索质量的同时，索引体积和搜索速度更优。

---

## 替代方案：OpenAI text-embedding-3-small

| 属性 | 说明 |
|------|------|
| 模型 | text-embedding-3-small |
| 类型 | OpenAI API 调用 |
| 向量维度 | 1536 |
| 费用 | $0.02 / 1M tokens（约 20 万条中文文本） |
| 速度 | 比本地模型快 3-5 倍 |

**适合场景：**
- 知识库非常庞大（10 万 + 文档）
- 你对检索速度要求高
- 已经依赖 OpenAI 生态，愿意多一层网络调用

**不适合场景：**
- 需要完全离线工作
- 不能或不想使用海外 API
- 知识库规模较小（几千条文档，本地模型足够）

---

## 如何切换模型

### 第一步：修改配置

编辑 `config.yaml`：

```yaml
# 使用默认模型（本地）
embedding_model: "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# 切换到 OpenAI（v2.0 支持）
embedding_model: "openai/text-embedding-3-small"
openai_api_key: "sk-xxxx"         # 需填入有效 API Key
openai_base_url: "https://api.openai.com/v1"  # 可选，支持代理中转
```

### 第二步：重新索引

切换模型后，**必须**使用 `--full` 参数重新索引，因为旧向量与新模型不兼容：

```bash
source .venv/bin/activate
cd scripts
python index.py index --full
```

### 第三步：验证

启动搜索验证模型切换成功：

```bash
python search.py "你的查询关键词"
```

---

## 网络问题与镜像配置

### 问题

首次下载 `paraphrase-multilingual-MiniLM-L12-v2` 时，HuggingFace 会自动从 huggingface.co 下载。在中国大陆可能遇到连接超时或下载极慢。

### 解决方案

设置环境变量使用 HuggingFace 镜像站：

```bash
# 临时设置（仅当前终端生效）
export HF_ENDPOINT=https://hf-mirror.com

# 或写入 shell 配置文件（永久生效）
echo 'export HF_ENDPOINT=https://hf-mirror.com' >> ~/.zshrc
source ~/.zshrc
```

设置后重启终端，再运行 `index.py` 即可从镜像站下载模型。

### 其他网络问题

- **pip 安装慢：** 使用清华镜像：`pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt`
- **SSL 证书错误：** 尝试关闭 SSL 验证（不推荐，仅临时用）：`export CURL_CA_BUNDLE=""`
