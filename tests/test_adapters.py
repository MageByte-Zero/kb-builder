"""Tests for SourceAdapter ABC and GitAdapter"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.sources.adapters import DocsAdapter, GitAdapter, RssAdapter, SourceAdapter


# -- SourceAdapter ABC --------------------------------------------------------


def test_source_adapter_is_abstract():
    """SourceAdapter 不能直接实例化"""
    with pytest.raises(TypeError):
        SourceAdapter()


# -- GitAdapter.validate_url --------------------------------------------------


def test_validate_git_url_https_with_git_suffix():
    adapter = GitAdapter()
    assert adapter.validate_url("https://github.com/user/repo.git") is True


def test_validate_git_url_https_without_git_suffix():
    adapter = GitAdapter()
    assert adapter.validate_url("https://github.com/user/repo") is True


def test_validate_git_url_ssh():
    adapter = GitAdapter()
    assert adapter.validate_url("git@github.com:user/repo.git") is True


def test_validate_git_url_trailing_slash():
    adapter = GitAdapter()
    assert adapter.validate_url("https://github.com/user/repo.git/") is True


def test_validate_git_url_strips_whitespace():
    adapter = GitAdapter()
    assert adapter.validate_url("  https://github.com/user/repo.git  ") is True


def test_validate_git_url_http():
    adapter = GitAdapter()
    assert adapter.validate_url("http://gitlab.com/user/repo.git") is True


def test_validate_git_url_gitee():
    adapter = GitAdapter()
    assert adapter.validate_url("https://gitee.com/user/repo.git") is True


def test_validate_git_url_invalid_empty():
    adapter = GitAdapter()
    assert adapter.validate_url("") is False


def test_validate_git_url_invalid_plain_text():
    adapter = GitAdapter()
    assert adapter.validate_url("not-a-url") is False


def test_validate_git_url_invalid_ftp():
    adapter = GitAdapter()
    assert adapter.validate_url("ftp://example.com/repo.git") is False


def test_validate_git_url_invalid_no_host():
    adapter = GitAdapter()
    assert adapter.validate_url("https://") is False


# -- GitAdapter.fetch ---------------------------------------------------------


def test_fetch_clone_new_repo():
    """首次 fetch 应执行 git clone"""
    adapter = GitAdapter()
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "repo"
        with patch.object(GitAdapter, "_run_git") as mock_run:
            result = adapter.fetch("https://github.com/user/repo.git", dest)
            assert result == dest
            assert dest.exists()
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert cmd[0:2] == ["git", "clone"]
            assert "--depth=1" in cmd


def test_fetch_pull_existing_repo():
    """已有 .git 目录时应执行 git pull"""
    adapter = GitAdapter()
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "repo"
        dest.mkdir()
        (dest / ".git").mkdir()
        with patch.object(GitAdapter, "_run_git") as mock_run:
            result = adapter.fetch("https://github.com/user/repo.git", dest)
            assert result == dest
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert "pull" in cmd
            assert "--ff-only" in cmd


def test_fetch_creates_dest_directory():
    """fetch 应自动创建 dest 目录"""
    adapter = GitAdapter()
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "nested" / "repo"
        assert not dest.exists()
        with patch.object(GitAdapter, "_run_git"):
            adapter.fetch("https://github.com/user/repo.git", dest)
            assert dest.exists()


def test_fetch_strips_url_whitespace():
    """fetch 应去除 URL 前后空格"""
    adapter = GitAdapter()
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "repo"
        with patch.object(GitAdapter, "_run_git") as mock_run:
            adapter.fetch("  https://github.com/user/repo.git  ", dest)
            cmd = mock_run.call_args[0][0]
            assert "https://github.com/user/repo.git" in cmd


def test_run_git_raises_on_failure():
    """_run_git 应在非零返回码时抛出 RuntimeError"""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=128, stderr="fatal: repository not found"
        )
        with pytest.raises(RuntimeError, match="Git 命令失败"):
            GitAdapter._run_git(["git", "clone", "https://bad.url/repo.git"])


def test_run_git_success_no_error():
    """_run_git 成功时不抛异常"""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        GitAdapter._run_git(["git", "clone", "https://ok.url/repo.git"])


# -- DocsAdapter.validate_url --------------------------------------------------


def test_validate_docs_url():
    adapter = DocsAdapter()
    assert adapter.validate_url("https://docs.python.org/3/") is True
    assert adapter.validate_url("http://example.com/docs") is True
    assert adapter.validate_url("ftp://example.com") is False
    assert adapter.validate_url("") is False


# -- DocsAdapter._safe_filename ------------------------------------------------


def test_safe_filename():
    adapter = DocsAdapter()
    assert adapter._safe_filename("Hello World") == "Hello_World"
    assert adapter._safe_filename('file<>:"/\\name') == "file______name"
    assert adapter._safe_filename("") == "page"


# -- DocsAdapter.fetch --------------------------------------------------------


def test_fetch_writes_markdown_to_dest():
    """fetch 应将 HTML 页面转换为 .md 文件写入 dest"""
    html = (
        "<html><head><title>Test Page</title></head>"
        "<body><article><h1>Hello</h1><p>World</p></article></body></html>"
    )
    mock_response = MagicMock()
    mock_response.text = html
    mock_response.status_code = 200

    adapter = DocsAdapter()
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "docs"
        with patch("scripts.sources.adapters.httpx.get", return_value=mock_response):
            result = adapter.fetch("https://example.com/docs", dest)
            assert result == dest
            md_files = list(dest.glob("*.md"))
            assert len(md_files) >= 1
            content = md_files[0].read_text(encoding="utf-8")
            assert "Test Page" in content
            assert "Hello" in content


# -- RssAdapter.validate_url --------------------------------------------------


def test_validate_rss_url():
    adapter = RssAdapter()
    assert adapter.validate_url("https://blog.example.com/feed.xml") is True
    assert adapter.validate_url("https://example.com/rss") is True
    assert adapter.validate_url("https://example.com/atom.xml") is True
    assert adapter.validate_url("https://example.com/page.html") is False
    assert adapter.validate_url("") is False


def test_validate_rss_url_edge_cases():
    adapter = RssAdapter()
    assert adapter.validate_url("http://example.com/feed") is True
    assert adapter.validate_url("https://example.com/data.xml") is True
    assert adapter.validate_url("https://example.com/atom") is True
    assert adapter.validate_url("ftp://example.com/feed.xml") is False
    assert adapter.validate_url("  https://example.com/rss  ") is True


# -- RssAdapter._safe_filename ------------------------------------------------


def test_rss_safe_filename():
    assert RssAdapter._safe_filename("Hello World") == "Hello_World"
    assert RssAdapter._safe_filename('file<>:"/\\name') == "file______name"
    assert RssAdapter._safe_filename("") == "entry"
    assert RssAdapter._safe_filename("  . ") == "entry"


# -- RssAdapter.fetch ---------------------------------------------------------


def test_fetch_rss_writes_markdown_files():
    """fetch 应将 RSS 条目写入独立 .md 文件"""
    mock_feed = MagicMock()
    mock_feed.bozo = False
    mock_feed.entries = [
        {
            "title": "First Post",
            "content": [{"value": "<p>Hello World</p>"}],
            "link": "https://example.com/first",
            "published": "2025-01-01",
        },
        {
            "title": "Second Post",
            "summary": "Summary text",
            "link": "https://example.com/second",
            "published": "2025-01-02",
        },
    ]

    adapter = RssAdapter()
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "rss"
        with patch("feedparser.parse", return_value=mock_feed):
            result = adapter.fetch("https://example.com/feed.xml", dest)
            assert result == dest
            md_files = sorted(dest.glob("*.md"))
            assert len(md_files) == 2
            content0 = md_files[0].read_text(encoding="utf-8")
            assert "# First Post" in content0
            assert "Hello World" in content0
            assert "原文: https://example.com/first" in content0
            content1 = md_files[1].read_text(encoding="utf-8")
            assert "# Second Post" in content1
            assert "Summary text" in content1


def test_fetch_rss_creates_dest_directory():
    """fetch 应自动创建 dest 目录"""
    mock_feed = MagicMock()
    mock_feed.bozo = False
    mock_feed.entries = [{"title": "Test", "summary": "body"}]

    adapter = RssAdapter()
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "nested" / "rss"
        assert not dest.exists()
        with patch("feedparser.parse", return_value=mock_feed):
            adapter.fetch("https://example.com/feed.xml", dest)
            assert dest.exists()


def test_fetch_rss_raises_on_parse_error():
    """bozo 且无条目时应抛出 RuntimeError"""
    mock_feed = MagicMock()
    mock_feed.bozo = True
    mock_feed.entries = []
    mock_feed.bozo_exception = Exception("malformed XML")

    adapter = RssAdapter()
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "rss"
        with patch("feedparser.parse", return_value=mock_feed):
            with pytest.raises(RuntimeError, match="RSS 解析失败"):
                adapter.fetch("https://example.com/bad.xml", dest)


def test_fetch_rss_empty_feed():
    """空条目列表应正常返回空目录"""
    mock_feed = MagicMock()
    mock_feed.bozo = False
    mock_feed.entries = []

    adapter = RssAdapter()
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "rss"
        with patch("feedparser.parse", return_value=mock_feed):
            result = adapter.fetch("https://example.com/empty.xml", dest)
            assert result == dest
            assert list(dest.glob("*.md")) == []


def test_fetch_rss_uses_description_fallback():
    """没有 content/summary 时应回退到 description"""
    mock_feed = MagicMock()
    mock_feed.bozo = False
    mock_feed.entries = [
        {"title": "Desc Entry", "description": "desc content"},
    ]

    adapter = RssAdapter()
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "rss"
        with patch("feedparser.parse", return_value=mock_feed):
            adapter.fetch("https://example.com/feed.xml", dest)
            md_files = list(dest.glob("*.md"))
            assert len(md_files) == 1
            assert "desc content" in md_files[0].read_text(encoding="utf-8")
