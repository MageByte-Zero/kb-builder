#!/usr/bin/env python3
"""KB Builder Web UI — FastAPI 应用"""

import os
import sys
from pathlib import Path

# 确保能 import scripts/index.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from index import RAGIndexer, load_config, ConfigError
from sources.manager import SourceManager
from sources.adapters import GitAdapter, DocsAdapter, RssAdapter

# ── 项目根目录（web.py 的父目录 = web/ 的父目录）──────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ── Singleton indexer ───────────────────────────────────────────

_indexer: RAGIndexer | None = None


def get_indexer() -> RAGIndexer:
    """全局单例，避免每次请求重新加载 Chroma"""
    global _indexer
    if _indexer is not None:
        return _indexer

    config_path = os.environ.get(
        "KB_CONFIG_PATH",
        str(PROJECT_ROOT / "scripts" / "config.yaml"),
    )

    try:
        config = load_config(config_path)
    except ConfigError as e:
        raise RuntimeError(f"配置加载失败: {e}")

    # 工作目录切到配置文件所在目录（与 MCP server 保持一致）
    os.chdir(Path(config_path).parent)
    _indexer = RAGIndexer(config)
    return _indexer


# ── FastAPI App ─────────────────────────────────────────────────

app = FastAPI(title="KB Builder Web UI", version="1.0.0")

# CORS — 开发阶段允许所有来源
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Jinja2 模板
TEMPLATES_DIR = Path(__file__).parent / "templates"
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ── Source Manager Singleton ──────────────────────────────────
_source_manager: SourceManager | None = None


def get_source_manager() -> SourceManager:
    global _source_manager
    if _source_manager is None:
        cfg_path = os.environ.get(
            "KB_CONFIG_PATH",
            str(PROJECT_ROOT / "scripts" / "config.yaml"),
        )
        sources_dir = os.path.expanduser("~/.kb-builder/sources")
        db_path = str(Path(cfg_path).parent / "sources.json")
        _source_manager = SourceManager(sources_dir=sources_dir, db_path=db_path)
    return _source_manager


ADAPTERS = {
    "git": GitAdapter,
    "docs": DocsAdapter,
    "rss": RssAdapter,
}


# ── Routes ──────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """渲染首页"""
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/api/search")
async def api_search(
    q: str = Query(..., description="检索关键词"),
    content_type: str = Query("all", description="内容类型过滤"),
    source: str = Query("all", description="来源过滤"),
    top_k: int = Query(5, ge=1, le=15, description="返回结果数"),
):
    """语义搜索知识库"""
    indexer = get_indexer()
    hits = indexer.search(
        query=q,
        top_k=top_k,
        content_type=content_type,
        source=source,
    )

    results = []
    for h in hits:
        results.append({
            "content": h["content"],
            "source": h["source"],
            "source_name": h.get("source_name", ""),
            "content_type": h.get("content_type", ""),
            "heading": h.get("heading", ""),
            "topic": h.get("topic", ""),
            "relevance_pct": round((1 - h["distance"]) * 100, 1),
            "source_path": h["source"],
        })

    return {"results": results}


@app.get("/api/topics")
async def api_topics():
    """列出知识库主题"""
    indexer = get_indexer()
    topics = indexer.get_topics()
    return {"topics": topics}


@app.get("/api/stats")
async def api_stats():
    """知识库索引统计"""
    indexer = get_indexer()
    stats = indexer.get_stats()
    return stats


@app.get("/api/article")
async def api_article(path: str = Query(..., description="文章 .md 文件路径")):
    """读取并返回单篇文章内容"""
    file_path = Path(path)

    # 如果是相对路径，从知识库内容源目录解析
    if not file_path.is_absolute():
        indexer = get_indexer()
        sources = indexer.config.get("content_sources", [])
        for src in sources:
            candidate = Path(os.path.expanduser(src["path"])) / path
            if candidate.exists():
                file_path = candidate
                break
        else:
            # fallback: 相对于项目根目录
            file_path = PROJECT_ROOT / path

    file_path = file_path.resolve()

    # 安全校验：必须是 .md 文件且存在
    if not file_path.exists():
        raise HTTPException(status_code=404, detail={"error": f"文件不存在: {path}"})
    if file_path.suffix.lower() != ".md":
        raise HTTPException(status_code=400, detail={"error": "仅支持 .md 文件"})

    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            content = file_path.read_text(encoding="gbk")
        except Exception:
            raise HTTPException(
                status_code=500,
                detail={"error": f"无法读取文件（编码不支持）: {path}"},
            )

    # 提取第一个标题作为 title
    import re
    match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    title = match.group(1).strip() if match else file_path.stem

    return {
        "title": title,
        "content": content,
        "path": str(file_path),
    }


# ── Source Management API ─────────────────────────────────────

@app.get("/api/sources")
async def list_sources():
    """列出所有知识库来源"""
    sm = get_source_manager()
    sources = sm.list()
    return {"sources": [
        {
            "id": s.id, "name": s.name, "type": s.type, "url": s.url,
            "enabled": s.enabled, "status": s.status,
            "error_message": s.error_message,
            "last_synced": s.last_synced, "chunk_count": s.chunk_count,
            "created_at": s.created_at,
        }
        for s in sources
    ]}


@app.post("/api/sources")
async def add_source(request: Request):
    """添加新来源"""
    body = await request.json()
    name = body.get("name", "").strip()
    source_type = body.get("type", "").strip()
    url = body.get("url", "").strip()

    if not name or not source_type or not url:
        raise HTTPException(status_code=400, detail={"error": "name, type, url 均为必填"})

    adapter_cls = ADAPTERS.get(source_type)
    if not adapter_cls:
        raise HTTPException(status_code=400, detail={"error": f"不支持的类型: {source_type}，可选: {list(ADAPTERS.keys())}"})

    adapter = adapter_cls()
    if not adapter.validate_url(url):
        raise HTTPException(status_code=400, detail={"error": "URL 格式不合法"})

    sm = get_source_manager()
    src = sm.add(name=name, source_type=source_type, url=url)

    # 后台异步执行 fetch + index
    import asyncio
    asyncio.create_task(_sync_source(src.id))

    return {
        "id": src.id, "name": src.name, "type": src.type,
        "status": src.status, "message": "已添加，正在后台同步...",
    }


@app.delete("/api/sources/{source_id}")
async def delete_source(source_id: str, remove_files: bool = True):
    """删除来源"""
    sm = get_source_manager()
    if not sm.delete(source_id, remove_files=remove_files):
        raise HTTPException(status_code=404, detail={"error": "来源不存在"})
    return {"message": "已删除"}


@app.post("/api/sources/{source_id}/sync")
async def sync_source(source_id: str):
    """重新同步+索引"""
    sm = get_source_manager()
    src = sm.get(source_id)
    if not src:
        raise HTTPException(status_code=404, detail={"error": "来源不存在"})

    import asyncio
    asyncio.create_task(_sync_source(source_id))

    return {"message": "正在同步...", "status": "syncing"}


@app.put("/api/sources/{source_id}/toggle")
async def toggle_source(source_id: str):
    """启用/禁用来源"""
    sm = get_source_manager()
    src = sm.toggle(source_id)
    if not src:
        raise HTTPException(status_code=404, detail={"error": "来源不存在"})
    return {"id": src.id, "enabled": src.enabled, "status": src.status}


async def _sync_source(source_id: str):
    """后台任务：fetch → index"""
    import asyncio
    sm = get_source_manager()
    src = sm.get(source_id)
    if not src:
        return

    adapter_cls = ADAPTERS.get(src.type)
    if not adapter_cls:
        sm.update(source_id, status="error", error_message=f"未知类型: {src.type}")
        return

    adapter = adapter_cls()
    dest = Path(src.local_path)

    try:
        sm.update(source_id, status="syncing", error_message="")
        # fetch 在线程池中执行（避免阻塞事件循环）
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, adapter.fetch, src.url, dest)
        sm.update(source_id, status="indexing")

        # 索引
        indexer = get_indexer()
        from index import load_markdown_files, chunk_document, _determine_content_type
        docs = load_markdown_files(str(dest))
        content_type = _determine_content_type(str(dest))
        chunking = indexer.config.get("chunking", {})
        max_size = chunking.get("brief_max_size", 600) if content_type == "brief" else chunking.get("article_max_size", 800)

        all_chunks = []
        for doc in docs:
            chunks = chunk_document(doc, content_type, max_size=max_size)
            all_chunks.extend(chunks)

        written = indexer.index_documents(all_chunks, src.name, content_type)
        sm.update(source_id, status="ready", chunk_count=written)

    except Exception as e:
        sm.update(source_id, status="error", error_message=str(e)[:500])
