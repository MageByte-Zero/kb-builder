"""Source Adapters — 拉取不同来源类型的内容到本地"""

import re
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from markdownify import markdownify as md


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


class DocsAdapter(SourceAdapter):
    """在线文档站适配器 — 抓取 HTML 页面转 Markdown"""

    def validate_url(self, url: str) -> bool:
        url = url.strip()
        return url.startswith("http://") or url.startswith("https://")

    def fetch(self, url: str, dest: Path) -> Path:
        """抓取文档站首页及子页面，转为 .md 保存到 dest"""
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
        base_netloc = urlparse(base_url).netloc

        for link in links:
            if count >= max_pages:
                break
            href = link["href"]
            full_url = urljoin(base_url, href)

            # 只抓同域页面
            if urlparse(full_url).netloc != base_netloc:
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
            except Exception as e:
                print(f"[WARN] 抓取子页面失败 {full_url}: {e}")
                continue

    @staticmethod
    def _safe_filename(name: str) -> str:
        """将标题转为安全文件名"""
        safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
        safe = safe.strip('. ')
        return (safe[:80] or "page").replace(' ', '_')
