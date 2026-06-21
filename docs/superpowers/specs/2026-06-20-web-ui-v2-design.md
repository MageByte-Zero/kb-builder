# KB Builder Web UI v2.0 — 设计文档

**日期:** 2026-06-20
**状态:** 已批准
**作者:** MageByte + Claude

## 1. 背景与目标

kb-builder 目前有两个入口：CLI（`index.py`）和 MCP（`kb_server.py`）。Web UI 是第三个入口，提供图形化的知识库检索体验。

**目标用户：**
- **个人使用**：本地启动，快速检索、验证索引质量
- **公开部署**：开源后其他用户可 clone 本地使用，也可部署到公网

**v2.0 范围：**
- F1 语义搜索
- F2 话题浏览（按 topic 分类）
- F3 统计面板
- F4 文章全文查看（Markdown 渲染）
- F5 过滤与排序（content_type、source、相关度）
- F6 键盘快捷键 — **deferred**

## 2. 架构

```
浏览器 (Alpine.js + fetch)
    ↓ JSON
FastAPI (web/app.py)
    ↓ import
RAGIndexer (scripts/index.py)
    ↓
ChromaDB (向量库)
```

**技术栈：**
- 后端：FastAPI + uvicorn（复用 RAGIndexer，不重新实现检索）
- 前端：单页 HTML + Alpine.js + marked.js + highlight.js（CDN，无构建步骤）
- 样式：自定义 CSS，深色科技感主题

**运行模式：**
- 本地：`python web.py` → `127.0.0.1:8000`
- 公开：`python web.py --host 0.0.0.0 --port 8000` → 配合 nginx/caddy 反代

**鉴权：** v2.0 无鉴权，后续按需加。

## 3. 文件结构

```
kb-builder/
├── web/
│   ├── __init__.py           # 空，标记为 Python 包
│   ├── app.py                # FastAPI 应用：API 路由 + 静态文件 + 模板渲染
│   ├── templates/
│   │   └── index.html        # 页面骨架（Alpine.js 驱动交互）
│   └── static/
│       ├── style.css         # 深色主题 + 渐变样式
│       └── app.js            # 搜索逻辑、状态管理、API 调用
├── web.py                    # 启动入口
├── scripts/                  # 现有
├── mcp/                      # 现有
└── requirements.txt          # 新增 fastapi, uvicorn, jinja2
```

## 4. API 接口

### GET /api/search
**参数：**
- `q` (string, 必填) — 搜索查询
- `content_type` (string, default="all") — 内容类型过滤
- `source` (string, default="all") — 来源过滤
- `top_k` (int, default=5, max=15) — 返回条数

**返回：**
```json
{
  "results": [{
    "content": "匹配的文本片段",
    "heading": "章节标题",
    "topic": "backend/redis",
    "source_name": "magebyte-ai-kb",
    "content_type": "article",
    "distance": 0.22,
    "relevance_pct": 78.0,
    "source_path": "/path/to/file.md"
  }]
}
```

### GET /api/topics
**返回：**
```json
{
  "topics": [{"key": "magebyte-ai-kb/backend/redis", "count": 45}]
}
```

### GET /api/stats
**返回：**
```json
{
  "collection": "unified_kb",
  "total_vectors": 5877,
  "sources": [{"name": "magebyte-ai-kb", "enabled": true, "path": "..."}]
}
```

### GET /api/article
**参数：**
- `path` (string, 必填) — .md 文件绝对路径

**返回：**
```json
{
  "title": "文章标题",
  "content": "原始 Markdown 内容",
  "path": "/path/to/file.md"
}
```

**错误格式：** `{"error": "错误信息"}`

## 5. 前端页面布局

```
┌──────────────────────────────────────────────────────────────┐
│  🔍 码哥字节 AI 知识库                    [Stats: 5877 chunks] │
├──────────────┬───────────────────────────────────────────────┤
│  话题导航     │  搜索区域                                      │
│              │  [输入框............] [类型▾] [搜索]            │
│  ▸ 全部      │                                               │
│  ▸ Redis     │  结果列表                                      │
│  ▸ JVM       │  ┌─────────────────────────────────────────┐  │
│  ▸ MySQL     │  │ 🔥 92%  Redis 持久化机制详解              │  │
│  ▸ Kafka     │  │ topic: backend/redis │ source: magebyte  │  │
│  ▸ AI Agent  │  │ "Redis 提供 RDB 和 AOF 两种持久化..."    │  │
│              │  └─────────────────────────────────────────┘  │
│  过滤器       │                                               │
│  ○ 全部类型   │  点击卡片 → 展开全文（Markdown 渲染）           │
│  ○ 硬核技术   │                                               │
│  ○ 场景踩坑   │                                               │
│  ○ 个人IP     │                                               │
│  ○ 行业热点   │                                               │
├──────────────┴───────────────────────────────────────────────┤
│  Footer                                                      │
└──────────────────────────────────────────────────────────────┘
```

**交互逻辑：**
- 左侧边栏：话题列表 + 内容类型单选 + 来源多选，点击触发搜索过滤
- 搜索栏：Enter 触发搜索
- 结果卡片：显示相关度百分比（>85% 绿、70-85% 黄、<70% 灰）、标题、话题、摘要
- 全文查看：点击卡片 → 结果区切换为文章全文，顶部有返回按钮
- 统计：右上角显示总条数，点击展开详细统计
- 响应式：窄屏时侧边栏折叠

## 6. 视觉风格

**配色（极简白 — Notion/Linear 风）：**
- 主背景：`#f8f9fb`
- 侧边栏/卡片：`#ffffff`
- 主色调：`#2563eb`（蓝）
- 正文文字：`#1a1a2e`
- 次要文字：`#6b7280`
- 相关度：>85% 绿 `#15803d` / 70-85% 黄 `#a16207` / <70% 灰 `#6b7280`
- 边框：`#e5e7eb`
- 代码块：深色底 `#1e1e2e`（保持可读性）

**字体：**
- 正文：-apple-system, Inter, Noto Sans SC（系统字体优先）
- 代码：JetBrains Mono, SF Mono

**动画：**
- 卡片出场：fadeInUp，依次延迟 50ms
- 侧边栏 hover：背景 `#f3f4f6` 过渡
- 搜索框 focus：蓝色边框 + 轻阴影

## 7. 依赖变更

`requirements.txt` 新增：
```
fastapi>=0.110.0
uvicorn>=0.27.0
jinja2>=3.1.0
```

`install.sh` 新增：安装上述依赖。

## 8. 动态知识库来源管理（v2.1 新增）

### 8.1 目标

支持从 Web UI 动态接入多种知识库来源，不再依赖手动编辑 `config.yaml`。

**支持的来源类型：**

| 类型 | 输入示例 | 行为 |
|------|----------|------|
| Git 仓库 | `https://github.com/user/repo.git` | clone → 索引所有 .md |
| 在线文档站 | `https://docs.example.com` | 抓取页面 → 转 Markdown → 索引 |
| 本地上传 | 拖拽 .md 文件 / .zip 包 | 解压 → 索引 |
| RSS/Atom | `https://blog.example.com/feed.xml` | 拉取条目 → 索引 |

### 8.2 数据模型

来源元数据持久化到 `scripts/sources.json`（替代直接编辑 config.yaml 中的 content_sources）：

```json
{
  "sources": [
    {
      "id": "src_a1b2c3",
      "name": "awesome-ai-kb",
      "type": "git",
      "url": "https://github.com/MageByte-Zero/awesome-ai-kb.git",
      "local_path": "~/.kb-builder/sources/awesome-ai-kb",
      "enabled": true,
      "status": "ready",
      "last_synced": "2026-06-20T15:30:00Z",
      "chunk_count": 1240,
      "created_at": "2026-06-20T10:00:00Z"
    }
  ]
}
```

**status 枚举：** `pending` | `syncing` | `indexing` | `ready` | `error`

### 8.3 API 新增接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/sources` | 列出所有来源 |
| POST | `/api/sources` | 添加新来源（body: `{name, type, url}`) |
| DELETE | `/api/sources/{id}` | 删除来源（可选删本地文件） |
| POST | `/api/sources/{id}/sync` | 重新同步+索引 |
| PUT | `/api/sources/{id}/toggle` | 启用/禁用 |

**POST /api/sources 返回：**
```json
{
  "id": "src_a1b2c3",
  "name": "awesome-ai-kb",
  "type": "git",
  "status": "syncing",
  "message": "正在克隆仓库..."
}
```

### 8.4 前端 UI

在侧边栏底部增加「知识库来源」管理入口，点击展开管理面板：

```
┌──────────────────────────────────────────────────────────────┐
│  知识库来源管理                                    [+ 添加来源] │
├──────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ 📦 awesome-ai-kb          [git]  ✅ 就绪  1240 chunks   │ │
│  │    github.com/MageByte-Zero/awesome-ai-kb               │ │
│  │    上次同步: 2 小时前            [同步] [删除]             │ │
│  ├─────────────────────────────────────────────────────────┤ │
│  │ 📚 rust-book              [docs] ⏳ 同步中...            │ │
│  │    doc.rust-lang.org/book                                │ │
│  │                                 [取消] [删除]             │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                              │
│  添加新来源:                                                  │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ 名称: [my-docs        ]  类型: [Git 仓库 ▾]              │ │
│  │ URL:  [https://github.com/user/repo.git              ]  │ │
│  │                                    [添加并索引]           │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

### 8.5 源适配器设计

每种来源类型实现统一接口：

```python
class SourceAdapter(ABC):
    @abstractmethod
    def fetch(self, url: str, dest: Path) -> Path:
        """拉取内容到本地目录，返回 .md 文件根目录"""

    @abstractmethod
    def validate_url(self, url: str) -> bool:
        """校验 URL 格式是否合法"""
```

**适配器实现：**
- `GitAdapter` — `git clone` / `git pull`，返回仓库根目录
- `DocsAdapter` — 用 `requests` + `BeautifulSoup` 抓取页面，`markdownify` 转 .md
- `RssAdapter` — `feedparser` 解析 feed，每条目存为独立 .md

**本地上传**不走适配器，直接保存到 `~/.kb-builder/sources/{id}/`。

### 8.6 目录约定

```
~/.kb-builder/
├── sources/              # 所有克隆/下载的来源内容
│   ├── src_a1b2c3/       # 按 source id 隔离
│   └── src_d4e5f6/
└── chroma_db/            # 向量库（现有）
```

`scripts/config.yaml` 中的 `content_sources` 保留向后兼容，系统启动时合并 `sources.json` + `config.yaml` 中的来源。

### 8.7 依赖变更

`requirements.txt` 新增：
```
httpx>=0.27.0
beautifulsoup4>=4.12.0
markdownify>=0.13.0
feedparser>=6.0.0
```

## 9. 不做的事（v2.0 scope out）

- 用户登录/鉴权
- 键盘快捷键
- 搜索历史
- 收藏/书签
- 移动端 App
- Docker 部署配置
- 定时自动同步（后续版本）
