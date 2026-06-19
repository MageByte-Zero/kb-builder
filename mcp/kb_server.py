#!/usr/bin/env python3
"""KB Builder MCP Server — 将知识库检索暴露为 Claude Code MCP 工具"""

import os
import sys
from pathlib import Path

# 确保能 import index 模块和同目录脚本
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from mcp.server.fastmcp import FastMCP
from index import load_config, ConfigError, RAGIndexer

mcp = FastMCP("AI Knowledge Base")

_indexer = None
_config = None


def get_indexer():
    """全局单例，避免每次调用重新加载 Chroma"""
    global _indexer, _config

    config_path = os.environ.get(
        "KB_CONFIG_PATH",
        str(Path(__file__).parent.parent / "scripts" / "config.yaml")
    )

    if _indexer is None or _config is None:
        try:
            _config = load_config(config_path)
        except ConfigError as e:
            raise RuntimeError(f"配置加载失败: {e}")

        os.chdir(Path(config_path).parent)
        _indexer = RAGIndexer(_config)

    return _indexer


@mcp.tool()
def search_kb(
    query: str,
    top_k: int = 5,
    content_type: str = "all",
    source: str = "all"
) -> str:
    """在码哥 AI 知识库中语义检索相关内容。

    覆盖 AI 编程工具、模型对比、RAG/Agent/MCP 架构、Prompt 工程、职场 AI 提效，
    以及后端技术栈：Redis/MySQL/JVM/Kafka/分布式/算法等。
    内容来自专栏原创、公众号文章和技术博客。

    当以下情况时使用此工具：
    - 需要了解某个 AI 技术概念的最新实践（如 RAG 分块策略）
    - 需要对比 AI 工具/模型的优劣
    - 需要查后端技术的实践经验（如 Redis 集群设计、JVM 调优）
    - 需要查 Prompt 模板或 AI 工作流
    - 需要在写技术文章时引用已整理好的资料

    Args:
        query: 自然语言描述你要查找的内容
        top_k: 返回结果数，默认 5，最大 15
        content_type: 过滤内容类型。article=原创文章, brief=信息摘要,
                      community=社区精华, all=不限制
        source: 过滤来源。magebyte-ai-kb=码哥知识库, my-kb=你的内容,
                all=不限制

    Returns:
        格式化的检索结果，每项包含：标题、内容片段、来源文件、相关度百分比
    """
    indexer = get_indexer()
    hits = indexer.search(
        query,
        top_k=min(top_k, 15),
        content_type=content_type,
        source=source
    )

    if not hits:
        return "未在知识库中找到相关文档。"

    parts = []
    parts.append(f"🔍 查询: {query}")
    parts.append(f"📝 找到 {len(hits)} 条相关结果:\n")

    for i, h in enumerate(hits, 1):
        relevance = max(0, 1 - h["distance"])
        topic_tag = f" [{h.get('topic', '')}]" if h.get('topic') else ""
        parts.append(
            f"### 结果 {i}: {h['source']}{topic_tag}\n"
            f"**章节**: {h.get('heading', '无标题')}\n"
            f"**相关度**: {relevance:.0%}\n"
            f"**来源**: {h.get('source_name', 'unknown')}\n\n"
            f"{h['content']}\n"
        )

    parts.append("---")
    parts.append(f"*检索条件: source={source}, content_type={content_type}, top_k={top_k}*")
    parts.append("*如需更多结果，可调整 top_k 参数或更换查询词。*")

    return "\n".join(parts)


@mcp.tool()
def list_kb_topics(category: str = "all") -> str:
    """列出知识库中已有的主题和内容概览。

    当你不确定知识库是否覆盖某个主题，或想浏览知识库的内容范围时，
    先用这个工具。也可以发现你可能不知道的已有内容。

    Args:
        category: 主题分类。可选值: ai, backend, all（默认）

    Returns:
        按主题分组的统计报告，包含各主题的 chunk 数量和简要描述
    """
    indexer = get_indexer()
    topics = indexer.get_topics()

    if not topics:
        return "知识库索引为空。请先运行 `python index.py index`。"

    # AI 相关和 backend 相关分类
    ai_keywords = {"ai", "chatgpt", "claude", "coding", "poweruser", "wechat"}
    parts = ["📚 知识库主题概览\n"]

    ai_topics = []
    backend_topics = []
    other_topics = []

    for t in topics:
        key_lower = t["key"].lower()
        if any(kw in key_lower for kw in ai_keywords):
            ai_topics.append(t)
        elif "brief" in key_lower or "community" in key_lower:
            other_topics.append(t)
        else:
            backend_topics.append(t)

    def print_group(title, group):
        if not group:
            return
        parts.append(f"## {title}\n")
        for t in group:
            parts.append(f"- **{t['key']}**: {t['count']} chunks")
        parts.append("")

    if category in ("all", "ai"):
        print_group("🤖 AI 与编程", ai_topics)
    if category in ("all", "backend"):
        print_group("⚙️ 后端技术栈", backend_topics)
    if category in ("all"):
        print_group("📋 其他", other_topics)

    return "\n".join(parts)


@mcp.tool()
def get_kb_stats() -> str:
    """查看知识库索引状态。

    当你想确认知识库内容是否是最新的，或排查检索结果不达预期时使用。
    显示总文档数、总向量数、各内容源统计。

    Returns:
        索引统计报告
    """
    indexer = get_indexer()
    stats = indexer.get_stats()

    parts = [
        "📊 知识库索引状态\n",
        f"**Collection**: `{stats['collection']}`",
        f"**总向量数**: {stats['total_vectors']}",
        f"**内容源**:\n",
    ]

    for s in stats.get("sources", stats.get("content_sources", [])):
        status = "✅ 已启用" if s.get("enabled") else "⏸️ 已禁用"
        parts.append(f"- `{s['name']}`: {s.get('path', '')} ({status})")

    if stats["total_vectors"] == 0:
        parts.append("\n⚠️ 索引为空！请运行:")
        parts.append("```bash")
        parts.append("cd ~/.claude/skills/kb-builder/scripts && python index.py index")
        parts.append("```")

    return "\n".join(parts)


if __name__ == "__main__":
    mcp.run(transport="stdio")
