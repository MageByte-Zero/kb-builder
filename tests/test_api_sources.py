"""Tests for source management API endpoints (mock-based)"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
import yaml

# Ensure import paths
sys.path.insert(0, str(Path(__file__).parent.parent / "web"))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from fastapi.testclient import TestClient


def _make_client(tmp_dir: str):
    """Create a test FastAPI client using a temporary directory.

    Returns (client, app_module) tuple. Caller must reset app_module singletons
    after use.
    """
    import web.app as app_module

    config = {
        "content_sources": [],
        "index": {
            "collection_name": "test",
            "persist_dir": os.path.join(tmp_dir, "chroma"),
            "device": "cpu",
        },
        "chunking": {"article_max_size": 800, "brief_max_size": 600},
    }
    cfg_path = os.path.join(tmp_dir, "config.yaml")
    with open(cfg_path, "w") as f:
        yaml.dump(config, f)

    os.environ["KB_CONFIG_PATH"] = cfg_path

    # Reset singletons
    app_module._source_manager = None
    app_module._indexer = None

    # Patch get_indexer so it does not initialize ChromaDB
    mock_indexer = MagicMock()
    mock_indexer.config = config
    patcher_indexer = patch.object(app_module, "get_indexer", return_value=mock_indexer)
    patcher_indexer.start()

    # Patch _sync_source to prevent background tasks from failing
    patcher_sync = patch.object(app_module, "_sync_source", new_callable=AsyncMock)
    patcher_sync.start()

    client = TestClient(app_module.app)
    return client, app_module, [patcher_indexer, patcher_sync]


def _cleanup(app_module, patchers):
    """Reset singletons and stop patchers."""
    app_module._source_manager = None
    app_module._indexer = None
    for p in patchers:
        p.stop()


# -- GET /api/sources ----------------------------------------------------------


def test_list_sources_empty():
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patchers = _make_client(tmp)
        try:
            resp = client.get("/api/sources")
            assert resp.status_code == 200
            assert resp.json()["sources"] == []
        finally:
            _cleanup(mod, patchers)


def test_list_sources_after_add():
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patchers = _make_client(tmp)
        try:
            resp = client.post(
                "/api/sources",
                json={"name": "test-kb", "type": "git", "url": "https://github.com/user/repo.git"},
            )
            assert resp.status_code == 200
            src_id = resp.json()["id"]

            resp = client.get("/api/sources")
            assert resp.status_code == 200
            sources = resp.json()["sources"]
            assert len(sources) == 1
            assert sources[0]["id"] == src_id
            assert sources[0]["name"] == "test-kb"
            assert sources[0]["type"] == "git"
            assert sources[0]["enabled"] is True
        finally:
            _cleanup(mod, patchers)


# -- POST /api/sources ---------------------------------------------------------


def test_add_source_git():
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patchers = _make_client(tmp)
        try:
            resp = client.post(
                "/api/sources",
                json={
                    "name": "my-repo",
                    "type": "git",
                    "url": "https://github.com/user/repo.git",
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["name"] == "my-repo"
            assert data["type"] == "git"
            assert data["id"].startswith("src_")
            assert "同步" in data["message"]
        finally:
            _cleanup(mod, patchers)


def test_add_source_docs():
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patchers = _make_client(tmp)
        try:
            resp = client.post(
                "/api/sources",
                json={
                    "name": "python-docs",
                    "type": "docs",
                    "url": "https://docs.python.org/3/",
                },
            )
            assert resp.status_code == 200
            assert resp.json()["type"] == "docs"
        finally:
            _cleanup(mod, patchers)


def test_add_source_rss():
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patchers = _make_client(tmp)
        try:
            resp = client.post(
                "/api/sources",
                json={
                    "name": "tech-blog",
                    "type": "rss",
                    "url": "https://blog.example.com/feed.xml",
                },
            )
            assert resp.status_code == 200
            assert resp.json()["type"] == "rss"
        finally:
            _cleanup(mod, patchers)


def test_add_source_missing_fields():
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patchers = _make_client(tmp)
        try:
            resp = client.post("/api/sources", json={"name": "test"})
            assert resp.status_code == 400
            assert "必填" in resp.json()["error"]
        finally:
            _cleanup(mod, patchers)


def test_add_source_missing_name():
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patchers = _make_client(tmp)
        try:
            resp = client.post(
                "/api/sources",
                json={"type": "git", "url": "https://github.com/u/r.git"},
            )
            assert resp.status_code == 400
        finally:
            _cleanup(mod, patchers)


def test_add_source_unsupported_type():
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patchers = _make_client(tmp)
        try:
            resp = client.post(
                "/api/sources",
                json={"name": "bad", "type": "ftp", "url": "https://example.com"},
            )
            assert resp.status_code == 400
            assert "不支持" in resp.json()["error"]
        finally:
            _cleanup(mod, patchers)


def test_add_source_invalid_url():
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patchers = _make_client(tmp)
        try:
            resp = client.post(
                "/api/sources",
                json={"name": "bad-url", "type": "git", "url": "not-a-url"},
            )
            assert resp.status_code == 400
            assert "URL" in resp.json()["error"]
        finally:
            _cleanup(mod, patchers)


def test_add_source_invalid_json():
    """POST with malformed body should return 400."""
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patchers = _make_client(tmp)
        try:
            resp = client.post(
                "/api/sources",
                content=b"{bad json",
                headers={"Content-Type": "application/json"},
            )
            assert resp.status_code == 400
            assert "JSON" in resp.json()["error"]
        finally:
            _cleanup(mod, patchers)


def test_add_source_duplicate_url():
    """POST with duplicate URL should return 409."""
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patchers = _make_client(tmp)
        try:
            resp = client.post(
                "/api/sources",
                json={"name": "first", "type": "git", "url": "https://github.com/u/r.git"},
            )
            assert resp.status_code == 200

            resp = client.post(
                "/api/sources",
                json={"name": "second", "type": "git", "url": "https://github.com/u/r.git"},
            )
            assert resp.status_code == 409
            assert "已存在" in resp.json()["error"]
        finally:
            _cleanup(mod, patchers)


# -- DELETE /api/sources/{source_id} -------------------------------------------


def test_delete_source():
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patchers = _make_client(tmp)
        try:
            resp = client.post(
                "/api/sources",
                json={"name": "to-delete", "type": "git", "url": "https://github.com/u/r.git"},
            )
            src_id = resp.json()["id"]

            resp = client.delete(f"/api/sources/{src_id}")
            assert resp.status_code == 200
            assert "已删除" in resp.json()["message"]

            resp = client.get("/api/sources")
            assert len(resp.json()["sources"]) == 0
        finally:
            _cleanup(mod, patchers)


def test_delete_source_not_found():
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patchers = _make_client(tmp)
        try:
            resp = client.delete("/api/sources/nonexistent")
            assert resp.status_code == 404
        finally:
            _cleanup(mod, patchers)


def test_delete_source_without_removing_files():
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patchers = _make_client(tmp)
        try:
            resp = client.post(
                "/api/sources",
                json={"name": "keep-files", "type": "git", "url": "https://github.com/u/r.git"},
            )
            src_id = resp.json()["id"]

            resp = client.delete(f"/api/sources/{src_id}?remove_files=false")
            assert resp.status_code == 200
        finally:
            _cleanup(mod, patchers)


# -- POST /api/sources/{source_id}/sync ----------------------------------------


def test_sync_source():
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patchers = _make_client(tmp)
        try:
            resp = client.post(
                "/api/sources",
                json={"name": "sync-me", "type": "git", "url": "https://github.com/u/r.git"},
            )
            src_id = resp.json()["id"]

            resp = client.post(f"/api/sources/{src_id}/sync")
            assert resp.status_code == 200
            assert "同步" in resp.json()["message"]
            assert resp.json()["status"] == "syncing"
        finally:
            _cleanup(mod, patchers)


def test_sync_source_not_found():
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patchers = _make_client(tmp)
        try:
            resp = client.post("/api/sources/nonexistent/sync")
            assert resp.status_code == 404
        finally:
            _cleanup(mod, patchers)


def test_sync_source_concurrent_guard():
    """Syncing a source that is already syncing should return 409."""
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patchers = _make_client(tmp)
        try:
            resp = client.post(
                "/api/sources",
                json={"name": "busy", "type": "git", "url": "https://github.com/u/r.git"},
            )
            src_id = resp.json()["id"]

            # Manually set status to syncing
            sm = mod.get_source_manager()
            sm.update(src_id, status="syncing")

            resp = client.post(f"/api/sources/{src_id}/sync")
            assert resp.status_code == 409
            assert "同步中" in resp.json()["error"]

            # Also test indexing status
            sm.update(src_id, status="indexing")
            resp = client.post(f"/api/sources/{src_id}/sync")
            assert resp.status_code == 409
        finally:
            _cleanup(mod, patchers)


# -- PUT /api/sources/{source_id}/toggle ---------------------------------------


def test_toggle_source():
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patchers = _make_client(tmp)
        try:
            resp = client.post(
                "/api/sources",
                json={"name": "toggle-me", "type": "git", "url": "https://github.com/u/r.git"},
            )
            src_id = resp.json()["id"]

            # Toggle off
            resp = client.put(f"/api/sources/{src_id}/toggle")
            assert resp.status_code == 200
            data = resp.json()
            assert data["id"] == src_id
            assert data["enabled"] is False

            # Toggle back on
            resp = client.put(f"/api/sources/{src_id}/toggle")
            assert resp.status_code == 200
            assert resp.json()["enabled"] is True
        finally:
            _cleanup(mod, patchers)


def test_toggle_source_not_found():
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patchers = _make_client(tmp)
        try:
            resp = client.put("/api/sources/nonexistent/toggle")
            assert resp.status_code == 404
        finally:
            _cleanup(mod, patchers)


# -- Response schema checks ---------------------------------------------------


def test_list_response_has_all_fields():
    """Verify the list response contains all expected fields."""
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patchers = _make_client(tmp)
        try:
            client.post(
                "/api/sources",
                json={"name": "schema-check", "type": "git", "url": "https://github.com/u/r.git"},
            )
            resp = client.get("/api/sources")
            source = resp.json()["sources"][0]
            expected_keys = {
                "id", "name", "type", "url", "enabled", "status",
                "error_message", "last_synced", "chunk_count", "created_at",
            }
            assert expected_keys == set(source.keys())
        finally:
            _cleanup(mod, patchers)


def test_add_response_has_expected_fields():
    """Verify the add response contains expected fields."""
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patchers = _make_client(tmp)
        try:
            resp = client.post(
                "/api/sources",
                json={"name": "field-check", "type": "git", "url": "https://github.com/u/r.git"},
            )
            data = resp.json()
            assert "id" in data
            assert "name" in data
            assert "type" in data
            assert "status" in data
            assert "message" in data
        finally:
            _cleanup(mod, patchers)


def test_error_response_format():
    """Verify error responses follow {"error": "msg", "status_code": N} format."""
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patchers = _make_client(tmp)
        try:
            resp = client.post("/api/sources", json={"name": "test"})
            assert resp.status_code == 400
            data = resp.json()
            assert "error" in data
            assert "status_code" in data
            assert data["status_code"] == 400
        finally:
            _cleanup(mod, patchers)
