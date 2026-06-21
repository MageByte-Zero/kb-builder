# Dynamic Source Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户从 Web UI 通过输入 URL 动态接入 Git 仓库、在线文档站、RSS feed 等多种知识库来源，支持完整 CRUD 管理。

**Architecture:** 新增 SourceManager（JSON 持久化）+ SourceAdapter（每种来源类型一个适配器）+ API 层（FastAPI 路由）+ 前端管理面板。现有 RAGIndexer 保持不变，SourceManager 负责协调"拉取 → 索引"流程。

**Tech Stack:** Python 3.10+, FastAPI, httpx, BeautifulSoup4, markdownify, feedparser, ChromaDB, Alpine.js

## Global Constraints

- 所有来源内容存储在 `~/.kb-builder/sources/{source_id}/`
- `sources.json` 路径: `scripts/sources.json`（与 config.yaml 同目录）
- 启动时合并 `sources.json` + `config.yaml` 中的来源（向后兼容）
- 每个适配器实现 `SourceAdapter` ABC 接口
- API 错误统一返回 `{"error": "message", "status_code": N}`
- 前端无构建步骤，Alpine.js + fetch

## File Structure

```
kb-builder/
├── scripts/
│   ├── sources/
│   │   ├── __init__.py
│   │   ├── manager.py          # SourceManager: CRUD + 持久化
│   │   └── adapters.py         # GitAdapter, DocsAdapter, RssAdapter
│   ├── index.py                # (modify) 新增 index_source() 方法
│   ├── config.yaml             # (existing)
│   └── sources.json            # (new) 运行时生成
├── web/
│   ├── app.py                  # (modify) 新增 /api/sources/* 路由
│   ├── templates/
│   │   └── index.html          # (modify) 新增来源管理面板
│   └── static/
│       ├── style.css           # (modify) 新增管理面板样式
│       └── app.js              # (modify) 新增来源管理逻辑
└── requirements.txt            # (modify) 新增依赖
```

---

### Task 1: SourceManager — 数据模型与持久化

**Files:**
- Create: `scripts/sources/__init__.py`
- Create: `scripts/sources/manager.py`
- Create: `tests/test_manager.py`

**Interfaces:**
- Produces: `SourceManager` class with methods `list()`, `add()`, `get()`, `update()`, `delete()`, `toggle()`

- [ ] **Step 1: 创建 sources 包和数据模型**

```python
# scripts/sources/__init__.py
from .manager import SourceManager
```

```python
# scripts/sources/manager.py
"""SourceManager — 知识库来源的 CRUD 与持久化"""

import json
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict


@dataclass
class Source:
    """一个知识库来源的元数据"""
    id: str = ""
    name: str = ""
    type: str = ""          # git | docs | rss | upload
    url: str = ""
    local_path: str = ""
    enabled: bool = True
    status: str = "pending"  # pending | syncing | indexing | ready | error
    error_message: str = ""
    last_synced: str = ""
    chunk_count: int = 0
    created_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = f"src_{uuid.uuid4().hex[:8]}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


class SourceManager:
    """管理知识库来源的 CRUD 操作，持久化到 sources.json"""

    def __init__(self, sources_dir: str = None, db_path: str = None):
        self.sources_dir = Path(sources_dir or os.path.expanduser("~/.kb-builder/sources"))
        self.sources_dir.mkdir(parents=True, exist_ok=True)

        self.db_path = Path(db_path or "sources.json")
        self._sources: Dict[str, Source] = {}
        self._load()

    def _load(self):
        """从 sources.json 加载"""
        if not self.db_path.exists():
            return
        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data.get("sources", []):
                src = Source(**item)
                self._sources[src.id] = src
        except (json.JSONDecodeError, TypeError) as e:
            print(f"[WARN] sources.json 解析失败: {e}")

    def _save(self):
        """持久化到 sources.json"""
        data = {"sources": [asdict(s) for s in self._sources.values()]}
        with open(self.db_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def list(self) -> List[Source]:
        """列出所有来源"""
        return list(self._sources.values())

    def get(self, source_id: str) -> Optional[Source]:
        """获取单个来源"""
        return self._sources.get(source_id)

    def add(self, name: str, source_type: str, url: str) -> Source:
        """添加新来源"""
        src = Source(name=name, type=source_type, url=url)
        src.local_path = str(self.sources_dir / src.id)
        self._sources[src.id] = src
        self._save()
        return src

    def update(self, source_id: str, **kwargs) -> Optional[Source]:
        """更新来源字段"""
        src = self._sources.get(source_id)
        if not src:
            return None
        for k, v in kwargs.items():
            if hasattr(src, k):
                setattr(src, k, v)
        self._save()
        return src

    def delete(self, source_id: str, remove_files: bool = True) -> bool:
        """删除来源，可选删除本地文件"""
        src = self._sources.pop(source_id, None)
        if src is None:
            return False
        if remove_files and src.local_path:
            import shutil
            p = Path(src.local_path)
            if p.exists():
                shutil.rmtree(p, ignore_errors=True)
        self._save()
        return True

    def toggle(self, source_id: str) -> Optional[Source]:
        """切换启用/禁用"""
        src = self._sources.get(source_id)
        if not src:
            return None
        src.enabled = not src.enabled
        self._save()
        return src
```

- [ ] **Step 2: 编写单元测试**

```python
# tests/test_manager.py
import json
import os
import tempfile
from pathlib import Path
from scripts.sources.manager import SourceManager, Source


def test_add_source():
    with tempfile.TemporaryDirectory() as tmp:
        sm = SourceManager(sources_dir=tmp, db_path=os.path.join(tmp, "sources.json"))
        src = sm.add("test-kb", "git", "https://github.com/test/repo.git")
        assert src.name == "test-kb"
        assert src.type == "git"
        assert src.id.startswith("src_")
        assert src.status == "pending"
        assert src.enabled is True


def test_list_sources():
    with tempfile.TemporaryDirectory() as tmp:
        sm = SourceManager(sources_dir=tmp, db_path=os.path.join(tmp, "sources.json"))
        sm.add("kb1", "git", "https://github.com/test/repo1.git")
        sm.add("kb2", "docs", "https://docs.example.com")
        sources = sm.list()
        assert len(sources) == 2
        assert {s.name for s in sources} == {"kb1", "kb2"}


def test_persistence():
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "sources.json")
        sm = SourceManager(sources_dir=tmp, db_path=db)
        src = sm.add("persistent-kb", "git", "https://github.com/test/repo.git")
        src_id = src.id

        # 新实例应能加载
        sm2 = SourceManager(sources_dir=tmp, db_path=db)
        loaded = sm2.get(src_id)
        assert loaded is not None
        assert loaded.name == "persistent-kb"


def test_delete_source():
    with tempfile.TemporaryDirectory() as tmp:
        sm = SourceManager(sources_dir=tmp, db_path=os.path.join(tmp, "sources.json"))
        src = sm.add("to-delete", "git", "https://github.com/test/repo.git")
        assert sm.delete(src.id, remove_files=False) is True
        assert sm.get(src.id) is None


def test_toggle_source():
    with tempfile.TemporaryDirectory() as tmp:
        sm = SourceManager(sources_dir=tmp, db_path=os.path.join(tmp, "sources.json"))
        src = sm.add("toggle-kb", "git", "https://github.com/test/repo.git")
        assert src.enabled is True
        toggled = sm.toggle(src.id)
        assert toggled.enabled is False
        toggled2 = sm.toggle(src.id)
        assert toggled2.enabled is True
```

- [ ] **Step 3: 运行测试**

```bash
cd /Users/magebte/Documents/GitHub/kb-builder
.venv/bin/python -m pytest tests/test_manager.py -v
```

Expected: 全部 PASS。

- [ ] **Step 4: 提交**

```bash
git add scripts/sources/ tests/test_manager.py
git commit -m "feat(sources): add SourceManager with JSON persistence and CRUD"
```

---

### Task 2: Source Adapters — Git 适配器

**Files:**
- Create: `scripts/sources/adapters.py`
- Create: `tests/test_adapters.py`

**Interfaces:**
- Produces: `SourceAdapter` ABC, `GitAdapter` class
- `GitAdapter.fetch(url, dest) -> Path`
- `GitAdapter.validate_url(url) -> bool`

- [ ] **Step 1: 定义 ABC 和 GitAdapter**

```python
# scripts/sources/adapters.py
"""Source Adapters — 拉取不同来源类型的内容到本地"""

import os
import re
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class SourceAdapter(ABC):
    """来源适配器基类"""

    @abstractmethod
    def fetch(self, url: str, dest: Path) -> Path:
        """拉取内容到 dest 目录，返回 .md 文件根目录"""

    @abstractmethod
    def validate_url(self, url: str) -> bool:
        """校验 URL 格式是否合法"""


class GitAdapter(SourceAdapter):
    """Git 仓库适配器"""

    GIT_URL_PATTERN = re.compile(
        r"^(https?://|git@)[\w./\-:@]+(\.git)?(/)?$"
    )

    def validate_url(self, url: str) -> bool:
        return bool(self.GIT_URL_PATTERN.match(url.strip()))

    def fetch(self, url: str, dest: Path) -> Path:
        """clone 或 pull 仓库到 dest"""
        url = url.strip()
        dest.mkdir(parents=True, exist_ok=True)

        git_dir = dest / ".git"
        if git_dir.exists():
            # 已存在，执行 pull
            self._run_git(["git", "-C", str(dest), "pull", "--ff-only"])
        else:
            # 首次 clone
            self._run_git(["git", "clone", "--depth=1", url, str(dest)])

        return dest

    @staticmethod
    def _run_git(cmd: list):
        """执行 git 命令，失败抛异常"""
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            raise RuntimeError(f"Git 命令失败: {' '.join(cmd)}\n{result.stderr.strip()}")
```

- [ ] **Step 2: 编写 GitAdapter 测试**

```python
# tests/test_adapters.py
from scripts.sources.adapters import GitAdapter


def test_validate_git_url_valid():
    adapter = GitAdapter()
    assert adapter.validate_url("https://github.com/user/repo.git") is True
    assert adapter.validate_url("https://github.com/user/repo") is True
    assert adapter.validate_url("git@github.com:user/repo.git") is True


def test_validate_git_url_invalid():
    adapter = GitAdapter()
    assert adapter.validate_url("") is False
    assert adapter.validate_url("not-a-url") is False
    assert adapter.validate_url("ftp://example.com/repo.git") is False
```

- [ ] **Step 3: 运行测试**

```bash
cd /Users/magebte/Documents/GitHub/kb-builder
.venv/bin/python -m pytest tests/test_adapters.py -v
```

Expected: 全部 PASS。

- [ ] **Step 4: 提交**

```bash
git add scripts/sources/adapters.py tests/test_adapters.py
git commit -m "feat(sources): add SourceAdapter ABC and GitAdapter"
```

---

### Task 3: Source Adapters — Docs 适配器

**Files:**
- Modify: `scripts/sources/adapters.py`
- Modify: `tests/test_adapters.py`

**Interfaces:**
- Produces: `DocsAdapter` class
- `DocsAdapter.fetch(url, dest) -> Path`
- `DocsAdapter.validate_url(url) -> bool`

- [ ] **Step 1: 实现 DocsAdapter**

在 `scripts/sources/adapters.py` 末尾追加：

```python
class DocsAdapter(SourceAdapter):
    """在线文档站适配器 — 抓取 HTML 页面转 Markdown"""

    def validate_url(self, url: str) -> bool:
        url = url.strip()
        return url.startswith("http://") or url.startswith("https://")

    def fetch(self, url: str, dest: Path) -> Path:
        """抓取文档站首页及子页面，转为 .md 保存到 dest"""
        import httpx
        from bs4 import BeautifulSoup
        from markdownify import markdownify as md

        dest.mkdir(parents=True, exist_ok=True)
        url = url.strip().rstrip("/")

        # 抓取首页
        resp = httpx.get(url, follow_redirects=True, timeout=30)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        title = soup.title.string.strip() if soup.title and soup.title.string else "index"

        # 提取正文（常见文档站选择器）
        content_el = (
            soup.select_one("article")
            or soup.select_one(".content")
            or soup.select_one(".markdown-body")
            or soup.select_one("main")
            or soup.body
        )

        if content_el:
            markdown_text = md(str(content_el), heading_style="ATX")
        else:
            markdown_text = md(resp.text, heading_style="ATX")

        # 写入 index.md
        file_path = dest / f"{self._safe_filename(title)}.md"
        file_path.write_text(f"# {title}\n\n{markdown_text}", encoding="utf-8")

        # 尝试抓取侧边栏链接（最多 50 个子页面）
        self._crawl_sidebar_links(soup, url, dest, max_pages=50)

        return dest

    def _crawl_sidebar_links(self, soup, base_url: str, dest: Path, max_pages: int = 50):
        """从侧边栏提取子页面链接并抓取"""
        import httpx
        from urllib.parse import urljoin
        from markdownify import markdownify as md

        # 常见侧边栏选择器
        nav = (
            soup.select_one("nav")
            or soup.select_one(".sidebar")
            or soup.select_one(".toc")
            or soup.select_one("[role='navigation']")
        )
        if not nav:
            return

        links = nav.find_all("a", href=True)
        visited = set()
        count = 0

        for link in links:
            if count >= max_pages:
                break
            href = link["href"]
            full_url = urljoin(base_url, href)

            # 只抓同域页面
            if not full_url.startswith(base_url.split("/")[0] + "//" + base_url.split("//")[1].split("/")[0]):
                continue
            if full_url in visited or "#" in href:
                continue

            visited.add(full_url)
            try:
                resp = httpx.get(full_url, follow_redirects=True, timeout=15)
                if resp.status_code != 200:
                    continue
                sub_soup = BeautifulSoup(resp.text, "html.parser")
                sub_content = (
                    sub_soup.select_one("article")
                    or sub_soup.select_one(".content")
                    or sub_soup.select_one("main")
                    or sub_soup.body
                )
                if sub_content:
                    sub_title = sub_soup.title.string.strip() if sub_soup.title and sub_soup.title.string else f"page_{count}"
                    sub_md = md(str(sub_content), heading_style="ATX")
                    sub_file = dest / f"{self._safe_filename(sub_title)}.md"
                    sub_file.write_text(f"# {sub_title}\n\n{sub_md}", encoding="utf-8")
                    count += 1
            except Exception:
                continue

    @staticmethod
    def _safe_filename(name: str) -> str:
        """将标题转为安全文件名"""
        safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
        safe = safe.strip('. ')
        return (safe[:80] or "page").replace(' ', '_')
```

- [ ] **Step 2: 编写 DocsAdapter 测试**

在 `tests/test_adapters.py` 追加：

```python
from scripts.sources.adapters import DocsAdapter


def test_validate_docs_url():
    adapter = DocsAdapter()
    assert adapter.validate_url("https://docs.python.org/3/") is True
    assert adapter.validate_url("http://example.com/docs") is True
    assert adapter.validate_url("ftp://example.com") is False
    assert adapter.validate_url("") is False


def test_safe_filename():
    adapter = DocsAdapter()
    assert adapter._safe_filename("Hello World") == "Hello_World"
    assert adapter._safe_filename('file<>:"/\\name') == "file______name"
    assert adapter._safe_filename("") == "page"
```

- [ ] **Step 3: 运行测试**

```bash
cd /Users/magebte/Documents/GitHub/kb-builder
.venv/bin/python -m pytest tests/test_adapters.py -v
```

Expected: 全部 PASS。

- [ ] **Step 4: 提交**

```bash
git add scripts/sources/adapters.py tests/test_adapters.py
git commit -m "feat(sources): add DocsAdapter for fetching online documentation"
```

---

### Task 4: Source Adapters — RSS 适配器

**Files:**
- Modify: `scripts/sources/adapters.py`
- Modify: `tests/test_adapters.py`

**Interfaces:**
- Produces: `RssAdapter` class
- `RssAdapter.fetch(url, dest) -> Path`
- `RssAdapter.validate_url(url) -> bool`

- [ ] **Step 1: 实现 RssAdapter**

在 `scripts/sources/adapters.py` 末尾追加：

```python
class RssAdapter(SourceAdapter):
    """RSS/Atom Feed 适配器"""

    def validate_url(self, url: str) -> bool:
        url = url.strip().lower()
        return (url.startswith("http://") or url.startswith("https://")) and (
            "feed" in url or "rss" in url or "atom" in url or url.endswith(".xml")
        )

    def fetch(self, url: str, dest: Path) -> Path:
        """拉取 RSS/Atom feed，每个条目存为独立 .md"""
        import feedparser

        dest.mkdir(parents=True, exist_ok=True)

        feed = feedparser.parse(url.strip())
        if feed.bozo and not feed.entries:
            raise RuntimeError(f"RSS 解析失败: {feed.bozo_exception}")

        for i, entry in enumerate(feed.entries):
            title = entry.get("title", f"entry_{i}")
            content = ""
            if entry.get("content"):
                content = entry["content"][0].get("value", "")
            elif entry.get("summary"):
                content = entry["summary"]
            elif entry.get("description"):
                content = entry["description"]

            link = entry.get("link", "")
            published = entry.get("published", "")

            safe_name = self._safe_filename(title)
            file_path = dest / f"{safe_name}.md"

            header = f"# {title}\n"
            if link:
                header += f"\n> 原文: {link}\n"
            if published:
                header += f"> 发布: {published}\n"

            file_path.write_text(f"{header}\n{content}", encoding="utf-8")

        return dest

    @staticmethod
    def _safe_filename(name: str) -> str:
        safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
        safe = safe.strip('. ')
        return (safe[:80] or "entry").replace(' ', '_')
```

- [ ] **Step 2: 编写 RssAdapter 测试**

在 `tests/test_adapters.py` 追加：

```python
from scripts.sources.adapters import RssAdapter


def test_validate_rss_url():
    adapter = RssAdapter()
    assert adapter.validate_url("https://blog.example.com/feed.xml") is True
    assert adapter.validate_url("https://example.com/rss") is True
    assert adapter.validate_url("https://example.com/atom.xml") is True
    assert adapter.validate_url("https://example.com/page.html") is False
    assert adapter.validate_url("") is False
```

- [ ] **Step 3: 运行测试**

```bash
cd /Users/magebte/Documents/GitHub/kb-builder
.venv/bin/python -m pytest tests/test_adapters.py -v
```

Expected: 全部 PASS。

- [ ] **Step 4: 提交**

```bash
git add scripts/sources/adapters.py tests/test_adapters.py
git commit -m "feat(sources): add RssAdapter for RSS/Atom feed ingestion"
```

---

### Task 5: API 层 — 来源管理路由

**Files:**
- Modify: `web/app.py`
- Create: `tests/test_api_sources.py`

**Interfaces:**
- Consumes: `SourceManager` from Task 1, `GitAdapter`/`DocsAdapter`/`RssAdapter` from Tasks 2-4
- Produces: 5 个 REST 端点

- [ ] **Step 1: 在 web/app.py 添加来源管理路由**

在 `web/app.py` 的 `from index import RAGIndexer, load_config, ConfigError` 之后，添加：

```python
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from sources.manager import SourceManager
from sources.adapters import GitAdapter, DocsAdapter, RssAdapter
```

在 `app` 定义之后、路由之前，添加：

```python
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
```

在现有路由之后，追加来源管理 API：

```python
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
```

- [ ] **Step 2: 编写 API 测试（mock 版）**

```python
# tests/test_api_sources.py
import tempfile
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# 确保 import 路径
sys.path.insert(0, str(Path(__file__).parent.parent / "web"))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


def _make_client(tmp_dir):
    """创建测试用的 FastAPI client，使用临时目录"""
    with patch.dict(os.environ, {"KB_CONFIG_PATH": os.path.join(tmp_dir, "config.yaml")}):
        # 写一个最小 config
        import yaml
        cfg = {
            "content_sources": [],
            "index": {"collection_name": "test", "persist_dir": os.path.join(tmp_dir, "chroma"), "device": "cpu"},
            "chunking": {"article_max_size": 800, "brief_max_size": 600},
        }
        with open(os.path.join(tmp_dir, "config.yaml"), "w") as f:
            yaml.dump(cfg, f)

        # 重置单例
        import web.app as app_module
        app_module._source_manager = None
        app_module._indexer = None

        client = TestClient(app_module.app)
        return client


def test_list_sources_empty():
    with tempfile.TemporaryDirectory() as tmp:
        client = _make_client(tmp)
        resp = client.get("/api/sources")
        assert resp.status_code == 200
        assert resp.json()["sources"] == []


def test_add_source_validation():
    with tempfile.TemporaryDirectory() as tmp:
        client = _make_client(tmp)
        # 缺字段
        resp = client.post("/api/sources", json={"name": "test"})
        assert resp.status_code == 400
```

- [ ] **Step 3: 安装新增依赖**

```bash
cd /Users/magebte/Documents/GitHub/kb-builder
.venv/bin/pip install httpx beautifulsoup4 markdownify feedparser
```

- [ ] **Step 4: 运行测试**

```bash
cd /Users/magebte/Documents/GitHub/kb-builder
.venv/bin/python -m pytest tests/test_api_sources.py -v
```

Expected: PASS（注意：`_sync_source` 是后台任务，测试中不会真正执行 fetch）。

- [ ] **Step 5: 更新 requirements.txt**

在 `requirements.txt` 末尾追加：

```
httpx>=0.27.0
beautifulsoup4>=4.12.0
markdownify>=0.13.0
feedparser>=6.0.0
```

- [ ] **Step 6: 提交**

```bash
git add web/app.py tests/test_api_sources.py requirements.txt
git commit -m "feat(api): add source management endpoints with async sync"
```

---

### Task 6: 前端 — 来源管理面板

**Files:**
- Modify: `web/templates/index.html`
- Modify: `web/static/app.js`
- Modify: `web/static/style.css`

**Interfaces:**
- Consumes: `/api/sources` (GET, POST, DELETE, POST sync, PUT toggle)
- Produces: 侧边栏来源管理面板 + 添加来源表单

- [ ] **Step 1: 在 index.html 侧边栏底部添加来源管理**

在 `</aside>` 之前（侧边栏最后），插入：

```html
<!-- Source Management -->
<div class="sidebar-section source-mgmt">
  <div class="sidebar-section-title">知识库来源</div>
  <button class="source-toggle-btn" @click="showSourcePanel = !showSourcePanel">
    <span x-text="showSourcePanel ? '收起管理' : '管理来源'"></span>
    <span class="source-count" x-text="sources.length"></span>
  </button>

  <!-- Source List -->
  <div x-show="showSourcePanel" x-collapse>
    <ul class="source-list">
      <template x-for="src in managedSources" :key="src.id">
        <li class="source-item" :class="{'source-error': src.status === 'error'}">
          <div class="source-item-top">
            <span class="source-type-badge" x-text="src.type"></span>
            <span class="source-name" x-text="src.name"></span>
            <span class="source-status" :class="'status-' + src.status"
                  x-text="statusText(src)"></span>
          </div>
          <div class="source-item-url" x-text="src.url" :title="src.url"></div>
          <div class="source-item-meta">
            <span x-show="src.chunk_count" x-text="src.chunk_count + ' chunks'"></span>
            <span x-show="src.last_synced" x-text="'同步: ' + timeAgo(src.last_synced)"></span>
          </div>
          <div class="source-item-error" x-show="src.error_message" x-text="src.error_message"></div>
          <div class="source-item-actions">
            <button class="source-action-btn" @click="syncSource(src.id)"
                    :disabled="src.status === 'syncing' || src.status === 'indexing'">
              同步
            </button>
            <button class="source-action-btn" @click="toggleSource(src.id)">
              <span x-text="src.enabled ? '禁用' : '启用'"></span>
            </button>
            <button class="source-action-btn source-action-danger" @click="deleteSource(src.id, src.name)">
              删除
            </button>
          </div>
        </li>
      </template>
    </ul>

    <!-- Add Source Form -->
    <div class="source-add-form">
      <input class="source-input" x-model="newSource.name" placeholder="名称 (如 my-docs)" />
      <select class="source-input" x-model="newSource.type">
        <option value="">选择类型</option>
        <option value="git">Git 仓库</option>
        <option value="docs">在线文档</option>
        <option value="rss">RSS/Atom</option>
      </select>
      <input class="source-input" x-model="newSource.url" placeholder="URL 地址" />
      <button class="source-add-btn" @click="addSource()"
              :disabled="!newSource.name || !newSource.type || !newSource.url">
        添加并索引
      </button>
    </div>
  </div>
</div>
```

- [ ] **Step 2: 在 app.js 添加来源管理逻辑**

在 Alpine.js data 对象中，添加以下属性和方法：

**新增属性（在 `sidebarOpen: false` 之后）：**
```javascript
showSourcePanel: false,
managedSources: [],
newSource: { name: '', type: '', url: '' },
```

**在 `init()` 中添加加载：**
```javascript
this.loadManagedSources(),
```

**新增方法：**
```javascript
async loadManagedSources() {
  try {
    const res = await fetch('/api/sources');
    if (res.ok) {
      const data = await res.json();
      this.managedSources = data.sources || [];
    }
  } catch (e) {
    console.error('Failed to load sources:', e);
  }
},

async addSource() {
  const { name, type, url } = this.newSource;
  if (!name || !type || !url) return;

  try {
    const res = await fetch('/api/sources', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, type, url })
    });
    if (res.ok) {
      this.newSource = { name: '', type: '', url: '' };
      await this.loadManagedSources();
      // 开始轮询状态
      this.pollSourceStatus();
    } else {
      const err = await res.json();
      alert(err.detail?.error || '添加失败');
    }
  } catch (e) {
    alert('网络错误: ' + e.message);
  }
},

async deleteSource(id, name) {
  if (!confirm(`确认删除「${name}」？本地文件也会被删除。`)) return;
  try {
    const res = await fetch(`/api/sources/${id}`, { method: 'DELETE' });
    if (res.ok) await this.loadManagedSources();
  } catch (e) {
    alert('删除失败: ' + e.message);
  }
},

async syncSource(id) {
  try {
    const res = await fetch(`/api/sources/${id}/sync`, { method: 'POST' });
    if (res.ok) {
      await this.loadManagedSources();
      this.pollSourceStatus();
    }
  } catch (e) {
    alert('同步失败: ' + e.message);
  }
},

async toggleSource(id) {
  try {
    const res = await fetch(`/api/sources/${id}/toggle`, { method: 'PUT' });
    if (res.ok) await this.loadManagedSources();
  } catch (e) {
    alert('操作失败: ' + e.message);
  }
},

pollSourceStatus() {
  // 每 3 秒轮询，直到所有来源都不是 syncing/indexing
  const poll = setInterval(async () => {
    await this.loadManagedSources();
    const hasActive = this.managedSources.some(
      s => s.status === 'syncing' || s.status === 'indexing'
    );
    if (!hasActive) {
      clearInterval(poll);
      // 重新加载 topics 和 stats
      this.loadTopics();
      this.loadStats();
    }
  }, 3000);
},

statusText(src) {
  const map = { pending: '等待中', syncing: '同步中...', indexing: '索引中...', ready: '就绪', error: '错误' };
  return map[src.status] || src.status;
},

timeAgo(iso) {
  if (!iso) return '';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return '刚刚';
  if (mins < 60) return mins + ' 分钟前';
  const hours = Math.floor(mins / 60);
  if (hours < 24) return hours + ' 小时前';
  return Math.floor(hours / 24) + ' 天前';
},
```

- [ ] **Step 3: 在 style.css 添加来源管理样式**

在 `/* Filter controls */` 之后追加：

```css
/* Source Management */
.source-mgmt {
  border-top: 1px solid #e8eaed;
  padding-top: 16px;
  margin-top: 8px;
}

.source-toggle-btn {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 6px 12px;
  background: none;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  font-size: 0.8125rem;
  color: #6b7280;
  cursor: pointer;
  transition: all 0.15s ease;
}

.source-toggle-btn:hover {
  background: #f9fafb;
  border-color: #d1d5db;
}

.source-count {
  background: #f3f4f6;
  padding: 1px 7px;
  border-radius: 10px;
  font-size: 0.6875rem;
  font-variant-numeric: tabular-nums;
}

.source-list {
  list-style: none;
  margin-top: 12px;
}

.source-item {
  padding: 10px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  margin-bottom: 8px;
  font-size: 0.75rem;
  transition: border-color 0.15s ease;
}

.source-item:hover {
  border-color: #d1d5db;
}

.source-item.source-error {
  border-color: #fca5a5;
  background: #fef2f2;
}

.source-item-top {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.source-type-badge {
  font-size: 0.625rem;
  font-weight: 600;
  text-transform: uppercase;
  background: #eff6ff;
  color: #2563eb;
  padding: 1px 5px;
  border-radius: 4px;
  letter-spacing: 0.04em;
}

.source-name {
  font-weight: 600;
  color: #1a1a2e;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-status {
  font-size: 0.625rem;
  padding: 1px 6px;
  border-radius: 4px;
}

.status-ready {
  background: #dcfce7;
  color: #15803d;
}

.status-syncing,
.status-indexing {
  background: #dbeafe;
  color: #2563eb;
}

.status-error {
  background: #fee2e2;
  color: #dc2626;
}

.status-pending {
  background: #f3f4f6;
  color: #6b7280;
}

.source-item-url {
  font-size: 0.6875rem;
  color: #9ca3af;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-bottom: 4px;
}

.source-item-meta {
  display: flex;
  gap: 8px;
  font-size: 0.6875rem;
  color: #9ca3af;
  margin-bottom: 4px;
}

.source-item-error {
  font-size: 0.6875rem;
  color: #dc2626;
  margin-bottom: 4px;
  word-break: break-all;
}

.source-item-actions {
  display: flex;
  gap: 6px;
  margin-top: 6px;
}

.source-action-btn {
  padding: 3px 8px;
  font-size: 0.6875rem;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  color: #6b7280;
  cursor: pointer;
  transition: all 0.15s ease;
}

.source-action-btn:hover {
  background: #f3f4f6;
  border-color: #d1d5db;
  color: #374151;
}

.source-action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.source-action-danger:hover {
  background: #fef2f2;
  border-color: #fca5a5;
  color: #dc2626;
}

/* Add Source Form */
.source-add-form {
  margin-top: 12px;
  padding: 10px;
  border: 1px dashed #d1d5db;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.source-input {
  padding: 6px 10px;
  font-size: 0.75rem;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #ffffff;
  color: #1a1a2e;
  font-family: inherit;
  outline: none;
  transition: border-color 0.15s ease;
}

.source-input:focus {
  border-color: #93c5fd;
}

.source-add-btn {
  padding: 6px 12px;
  font-size: 0.75rem;
  font-weight: 600;
  background: #2563eb;
  border: none;
  border-radius: 6px;
  color: #ffffff;
  cursor: pointer;
  transition: all 0.15s ease;
}

.source-add-btn:hover {
  background: #1d4ed8;
}

.source-add-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
```

- [ ] **Step 4: 验证前端**

启动 Web UI：

```bash
cd /Users/magebte/Documents/GitHub/kb-builder
.venv/bin/python web.py --port 8000
```

在浏览器打开 `http://127.0.0.1:8000`，检查：
1. 侧边栏底部出现「知识库来源」区域
2. 点击「管理来源」展开面板
3. 添加表单三个字段可输入
4. 已有来源（如果 sources.json 有数据）正确显示

- [ ] **Step 5: 提交**

```bash
git add web/templates/index.html web/static/app.js web/static/style.css
git commit -m "feat(web): add source management panel with CRUD UI"
```

---

### Task 7: 集成 — 统一来源加载与 config.yaml 兼容

**Files:**
- Modify: `scripts/index.py`

**Interfaces:**
- Consumes: `SourceManager.list()`
- Produces: `RAGIndexer.load_all_sources()` — 合并 sources.json + config.yaml

- [ ] **Step 1: 在 RAGIndexer 中添加统一来源加载**

在 `scripts/index.py` 的 `RAGIndexer` 类中，`index_all` 方法之前，添加：

```python
def get_merged_sources(self, source_manager=None) -> list:
    """合并 sources.json 和 config.yaml 中的来源（去重）"""
    sources = list(self.config.get("content_sources", []))

    if source_manager is None:
        try:
            from sources.manager import SourceManager
            source_manager = SourceManager()
        except ImportError:
            return sources

    for src in source_manager.list():
        if not src.enabled or src.status != "ready":
            continue
        # 去重：检查 local_path 是否已在 config 中
        if any(s.get("path") == src.local_path for s in sources):
            continue
        sources.append({
            "name": src.name,
            "path": src.local_path,
            "enabled": True,
        })

    return sources
```

修改 `index_all` 方法，使用 `get_merged_sources()` 替代直接读取 config：

```python
def index_all(self, full: bool = False):
    """遍历所有来源（config + sources.json），执行索引。"""
    sources = self.get_merged_sources()
    # ... 其余逻辑不变
```

- [ ] **Step 2: 验证向后兼容**

确认现有 `python scripts/index.py index` 仍然正常工作：

```bash
cd /Users/magebte/Documents/GitHub/kb-builder/scripts
../.venv/bin/python index.py stats
```

Expected: 正常输出 collection 信息，不报错。

- [ ] **Step 3: 提交**

```bash
git add scripts/index.py
git commit -m "feat(index): merge sources.json with config.yaml for unified source loading"
```

---

### Task 8: 端到端验证

- [ ] **Step 1: 完整流程测试**

```bash
cd /Users/magebte/Documents/GitHub/kb-builder

# 安装新依赖
.venv/bin/pip install -r requirements.txt

# 启动 Web UI
.venv/bin/python web.py --port 8000
```

在浏览器中测试：
1. 打开 `http://127.0.0.1:8000`
2. 侧边栏点击「管理来源」
3. 添加一个 Git 仓库来源（如 `https://github.com/MageByte-Zero/awesome-ai-kb.git`）
4. 观察状态从 `syncing` → `indexing` → `ready`
5. 刷新页面，来源列表正确显示
6. 用搜索功能验证新来源的内容可被检索
7. 测试删除来源
8. 测试同步（重新索引）

- [ ] **Step 2: 全量测试**

```bash
cd /Users/magebte/Documents/GitHub/kb-builder
.venv/bin/python -m pytest tests/ -v
```

Expected: 全部 PASS。

- [ ] **Step 3: 最终提交**

```bash
git add -A
git commit -m "feat: v2.1 dynamic source management — Git, docs, RSS, CRUD"
```
