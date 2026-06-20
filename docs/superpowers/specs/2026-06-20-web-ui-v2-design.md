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

**配色（深色科技感）：**
- 主背景：`#0a0a0f`
- 卡片背景：`#12121a`
- 主色调：渐变 `#6366f1 → #8b5cf6`（紫蓝）
- 正文文字：`#e2e8f0`
- 次要文字：`#94a3b8`
- 相关度：>85% 绿 `#22c55e` / 70-85% 黄 `#eab308` / <70% 灰 `#64748b`
- 边框：`rgba(255,255,255,0.06)`

**字体：**
- 正文：Inter（Google Fonts CDN）
- 代码：JetBrains Mono（Google Fonts CDN）

**动画：**
- 卡片出场：fadeInUp，依次延迟 50ms
- 侧边栏 hover：左侧渐变条滑入
- 全文展开：slide 过渡 200ms

## 7. 依赖变更

`requirements.txt` 新增：
```
fastapi>=0.110.0
uvicorn>=0.27.0
jinja2>=3.1.0
```

`install.sh` 新增：安装上述依赖。

## 8. 不做的事（v2.0 scope out）

- 用户登录/鉴权
- 键盘快捷键
- 搜索历史
- 收藏/书签
- 移动端 App
- Docker 部署配置
