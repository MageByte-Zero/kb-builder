"""Tests for SourceAdapter ABC and GitAdapter"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.sources.adapters import DocsAdapter, GitAdapter, SourceAdapter


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
