"""Tests for source management API endpoints (mock-based)"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

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
    patcher = patch.object(app_module, "get_indexer", return_value=mock_indexer)
    patcher.start()

    client = TestClient(app_module.app)
    return client, app_module, patcher


def _cleanup(app_module, patcher):
    """Reset singletons and stop patcher."""
    app_module._source_manager = None
    app_module._indexer = None
    patcher.stop()


# -- GET /api/sources ----------------------------------------------------------


def test_list_sources_empty():
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patcher = _make_client(tmp)
        try:
            resp = client.get("/api/sources")
            assert resp.status_code == 200
            assert resp.json()["sources"] == []
        finally:
            _cleanup(mod, patcher)


def test_list_sources_after_add():
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patcher = _make_client(tmp)
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
            _cleanup(mod, patcher)


# -- POST /api/sources ---------------------------------------------------------


def test_add_source_git():
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patcher = _make_client(tmp)
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
            _cleanup(mod, patcher)


def test_add_source_docs():
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patcher = _make_client(tmp)
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
            _cleanup(mod, patcher)


def test_add_source_rss():
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patcher = _make_client(tmp)
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
            _cleanup(mod, patcher)


def test_add_source_missing_fields():
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patcher = _make_client(tmp)
        try:
            resp = client.post("/api/sources", json={"name": "test"})
            assert resp.status_code == 400
            assert "必填" in resp.json()["detail"]["error"]
        finally:
            _cleanup(mod, patcher)


def test_add_source_missing_name():
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patcher = _make_client(tmp)
        try:
            resp = client.post(
                "/api/sources",
                json={"type": "git", "url": "https://github.com/u/r.git"},
            )
            assert resp.status_code == 400
        finally:
            _cleanup(mod, patcher)


def test_add_source_unsupported_type():
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patcher = _make_client(tmp)
        try:
            resp = client.post(
                "/api/sources",
                json={"name": "bad", "type": "ftp", "url": "https://example.com"},
            )
            assert resp.status_code == 400
            assert "不支持" in resp.json()["detail"]["error"]
        finally:
            _cleanup(mod, patcher)


def test_add_source_invalid_url():
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patcher = _make_client(tmp)
        try:
            resp = client.post(
                "/api/sources",
                json={"name": "bad-url", "type": "git", "url": "not-a-url"},
            )
            assert resp.status_code == 400
            assert "URL" in resp.json()["detail"]["error"]
        finally:
            _cleanup(mod, patcher)


# -- DELETE /api/sources/{source_id} -------------------------------------------


def test_delete_source():
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patcher = _make_client(tmp)
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
            _cleanup(mod, patcher)


def test_delete_source_not_found():
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patcher = _make_client(tmp)
        try:
            resp = client.delete("/api/sources/nonexistent")
            assert resp.status_code == 404
        finally:
            _cleanup(mod, patcher)


def test_delete_source_without_removing_files():
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patcher = _make_client(tmp)
        try:
            resp = client.post(
                "/api/sources",
                json={"name": "keep-files", "type": "git", "url": "https://github.com/u/r.git"},
            )
            src_id = resp.json()["id"]

            resp = client.delete(f"/api/sources/{src_id}?remove_files=false")
            assert resp.status_code == 200
        finally:
            _cleanup(mod, patcher)


# -- POST /api/sources/{source_id}/sync ----------------------------------------


def test_sync_source():
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patcher = _make_client(tmp)
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
            _cleanup(mod, patcher)


def test_sync_source_not_found():
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patcher = _make_client(tmp)
        try:
            resp = client.post("/api/sources/nonexistent/sync")
            assert resp.status_code == 404
        finally:
            _cleanup(mod, patcher)


# -- PUT /api/sources/{source_id}/toggle ---------------------------------------


def test_toggle_source():
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patcher = _make_client(tmp)
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
            _cleanup(mod, patcher)


def test_toggle_source_not_found():
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patcher = _make_client(tmp)
        try:
            resp = client.put("/api/sources/nonexistent/toggle")
            assert resp.status_code == 404
        finally:
            _cleanup(mod, patcher)


# -- Response schema checks ---------------------------------------------------


def test_list_response_has_all_fields():
    """Verify the list response contains all expected fields."""
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patcher = _make_client(tmp)
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
            _cleanup(mod, patcher)


def test_add_response_has_expected_fields():
    """Verify the add response contains expected fields."""
    with tempfile.TemporaryDirectory() as tmp:
        client, mod, patcher = _make_client(tmp)
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
            _cleanup(mod, patcher)
