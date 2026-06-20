"""SourceManager — 知识库来源的 CRUD 与持久化"""

import json
import os
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class Source:
    """一个知识库来源的元数据"""

    id: str = ""
    name: str = ""
    type: str = ""  # git | docs | rss | upload
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
        self.sources_dir = Path(
            sources_dir or os.path.expanduser("~/.kb-builder/sources")
        )
        self.sources_dir.mkdir(parents=True, exist_ok=True)

        self.db_path = Path(db_path) if db_path else Path("sources.json")
        self._sources: Dict[str, Source] = {}
        self._load()

    # -- persistence -----------------------------------------------------------

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

    # -- CRUD ------------------------------------------------------------------

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
