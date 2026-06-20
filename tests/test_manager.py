import json
import os
import tempfile
from pathlib import Path

from scripts.sources.manager import Source, SourceManager


# -- Source dataclass ----------------------------------------------------------


def test_source_defaults():
    """Source 自动生成 id 和 created_at"""
    src = Source()
    assert src.id.startswith("src_")
    assert src.created_at != ""
    assert src.enabled is True
    assert src.status == "pending"


def test_source_explicit_fields():
    """Source 接受显式字段"""
    src = Source(id="custom", name="kb", type="git", url="https://example.com")
    assert src.id == "custom"
    assert src.name == "kb"


# -- SourceManager CRUD -------------------------------------------------------


def test_add_source():
    with tempfile.TemporaryDirectory() as tmp:
        sm = SourceManager(sources_dir=tmp, db_path=os.path.join(tmp, "sources.json"))
        src = sm.add("test-kb", "git", "https://github.com/test/repo.git")
        assert src.name == "test-kb"
        assert src.type == "git"
        assert src.id.startswith("src_")
        assert src.status == "pending"
        assert src.enabled is True


def test_add_sets_local_path():
    with tempfile.TemporaryDirectory() as tmp:
        sm = SourceManager(sources_dir=tmp, db_path=os.path.join(tmp, "sources.json"))
        src = sm.add("kb", "git", "https://example.com")
        assert src.local_path == os.path.join(tmp, src.id)


def test_get_source():
    with tempfile.TemporaryDirectory() as tmp:
        sm = SourceManager(sources_dir=tmp, db_path=os.path.join(tmp, "sources.json"))
        src = sm.add("kb", "git", "https://example.com")
        assert sm.get(src.id) is src
        assert sm.get("nonexistent") is None


def test_list_sources():
    with tempfile.TemporaryDirectory() as tmp:
        sm = SourceManager(sources_dir=tmp, db_path=os.path.join(tmp, "sources.json"))
        sm.add("kb1", "git", "https://github.com/test/repo1.git")
        sm.add("kb2", "docs", "https://docs.example.com")
        sources = sm.list()
        assert len(sources) == 2
        assert {s.name for s in sources} == {"kb1", "kb2"}


def test_list_empty():
    with tempfile.TemporaryDirectory() as tmp:
        sm = SourceManager(sources_dir=tmp, db_path=os.path.join(tmp, "sources.json"))
        assert sm.list() == []


def test_update_source():
    with tempfile.TemporaryDirectory() as tmp:
        sm = SourceManager(sources_dir=tmp, db_path=os.path.join(tmp, "sources.json"))
        src = sm.add("kb", "git", "https://example.com")
        updated = sm.update(src.id, name="renamed", status="ready")
        assert updated.name == "renamed"
        assert updated.status == "ready"


def test_update_nonexistent():
    with tempfile.TemporaryDirectory() as tmp:
        sm = SourceManager(sources_dir=tmp, db_path=os.path.join(tmp, "sources.json"))
        assert sm.update("no-such-id", name="x") is None


def test_update_ignores_unknown_fields():
    with tempfile.TemporaryDirectory() as tmp:
        sm = SourceManager(sources_dir=tmp, db_path=os.path.join(tmp, "sources.json"))
        src = sm.add("kb", "git", "https://example.com")
        updated = sm.update(src.id, nonexistent_field="value")
        assert updated is not None
        assert not hasattr(updated, "nonexistent_field") or getattr(
            updated, "nonexistent_field", None
        ) is None


def test_delete_source():
    with tempfile.TemporaryDirectory() as tmp:
        sm = SourceManager(sources_dir=tmp, db_path=os.path.join(tmp, "sources.json"))
        src = sm.add("to-delete", "git", "https://github.com/test/repo.git")
        assert sm.delete(src.id, remove_files=False) is True
        assert sm.get(src.id) is None


def test_delete_nonexistent():
    with tempfile.TemporaryDirectory() as tmp:
        sm = SourceManager(sources_dir=tmp, db_path=os.path.join(tmp, "sources.json"))
        assert sm.delete("no-such-id") is False


def test_toggle_source():
    with tempfile.TemporaryDirectory() as tmp:
        sm = SourceManager(sources_dir=tmp, db_path=os.path.join(tmp, "sources.json"))
        src = sm.add("toggle-kb", "git", "https://github.com/test/repo.git")
        assert src.enabled is True
        toggled = sm.toggle(src.id)
        assert toggled.enabled is False
        toggled2 = sm.toggle(src.id)
        assert toggled2.enabled is True


def test_toggle_nonexistent():
    with tempfile.TemporaryDirectory() as tmp:
        sm = SourceManager(sources_dir=tmp, db_path=os.path.join(tmp, "sources.json"))
        assert sm.toggle("no-such-id") is None


# -- persistence --------------------------------------------------------------


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


def test_persistence_corrupted_json():
    """损坏的 JSON 不应崩溃，应加载为空"""
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "sources.json")
        with open(db, "w") as f:
            f.write("{bad json")
        sm = SourceManager(sources_dir=tmp, db_path=db)
        assert sm.list() == []


def test_persistence_missing_file():
    """不存在的 db_path 应加载为空"""
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "nonexistent.json")
        sm = SourceManager(sources_dir=tmp, db_path=db)
        assert sm.list() == []
