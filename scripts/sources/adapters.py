"""Source Adapters — 拉取不同来源类型的内容到本地"""

import re
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path


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
