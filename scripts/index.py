#!/usr/bin/env python3
"""KB Builder — 索引管道：加载 Markdown → 分块 → embedding → Chroma"""

import os
import re
import sys
import hashlib
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, field

import yaml


@dataclass
class Document:
    """一个文档块，携带内容和元数据"""
    content: str
    metadata: Dict[str, str] = field(default_factory=dict)


def load_config(config_path: str = "config.yaml") -> dict:
    """加载 config.yaml"""
    config_file = Path(config_path)
    if not config_file.exists():
        print(f"[ERROR] 配置文件不存在: {config_path}")
        print("请先编辑 config.yaml 声明你的内容源路径")
        sys.exit(1)
    with open(config_file, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_markdown_files(docs_dir: str) -> List[Document]:
    """遍历目录下所有 .md 文件，返回原始 Document 列表"""
    documents = []
    base = Path(docs_dir).expanduser().resolve()
    if not base.exists():
        print(f"[WARN] 目录不存在，跳过: {docs_dir}")
        return documents

    for md_file in base.rglob("*.md"):
        # 跳过 .git 目录和 node_modules
        if any(p.startswith('.') for p in md_file.parts if p != '.'):
            continue
        try:
            with open(md_file, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            try:
                with open(md_file, "r", encoding="gbk") as f:
                    content = f.read()
            except Exception:
                print(f"[WARN] 无法读取: {md_file}")
                continue

        if not content.strip():
            continue

        rel_path = str(md_file.relative_to(base))
        parent_dir = md_file.parent.name if md_file.parent != base else "root"
        # topic 从父目录名推断
        topic = parent_dir.lower().replace(" ", "-")

        documents.append(Document(
            content=content,
            metadata={
                "source_path": rel_path,
                "file_name": md_file.name,
                "file_mtime": str(md_file.stat().st_mtime),
                "topic": topic,
            }
        ))
    return documents


def _extract_heading(text: str) -> str:
    """提取文本的首个标题行作为 heading"""
    match = re.search(r"^(#{1,4})\s+(.+)$", text, re.MULTILINE)
    if match:
        return f"{match.group(1)} {match.group(2).strip()}"
    return ""


def _determine_content_type(source_dir: str) -> str:
    """根据来源目录推断内容类型"""
    source_lower = source_dir.lower()
    if "articles" in source_lower or "专栏" in source_lower or "wechat" in source_lower:
        return "article"
    if "briefs" in source_lower or "摘要" in source_lower:
        return "brief"
    if "community" in source_lower or "社区" in source_lower:
        return "community"
    # blogs/ 下的技术目录默认也是 article 类型
    return "article"


def chunk_article(doc: Document, max_size: int = 800) -> List[Document]:
    """策略 A：结构感知分块。按 ## 标题切，超限再按 ### 拆"""
    chunks = []
    # 按 ## 标题拆分
    sections = re.split(r"\n(?=## )", doc.content)

    for section in sections:
        if not section.strip():
            continue
        if len(section) <= max_size:
            chunks.append(Document(
                content=section.strip(),
                metadata={
                    **doc.metadata,
                    "heading": _extract_heading(section),
                }
            ))
        else:
            # 按 ### 继续拆
            subs = re.split(r"\n(?=### )", section)
            for sub in subs:
                if not sub.strip():
                    continue
                # 如果还是太长，按段落硬切
                if len(sub) > max_size:
                    paragraphs = sub.split("\n\n")
                    current = ""
                    for para in paragraphs:
                        if len(current) + len(para) + 2 <= max_size:
                            current += ("\n\n" + para) if current else para
                        else:
                            if current.strip():
                                chunks.append(Document(
                                    content=current.strip(),
                                    metadata={
                                        **doc.metadata,
                                        "heading": _extract_heading(sub),
                                    }
                                ))
                            current = para
                    if current.strip():
                        chunks.append(Document(
                            content=current.strip(),
                            metadata={
                                **doc.metadata,
                                "heading": _extract_heading(sub),
                            }
                        ))
                else:
                    chunks.append(Document(
                        content=sub.strip(),
                        metadata={
                            **doc.metadata,
                            "heading": _extract_heading(sub),
                        }
                    ))
    return chunks


def chunk_brief(doc: Document, max_size: int = 600) -> List[Document]:
    """策略 B：固定模板 / 段落分块"""
    chunks = []
    # 先尝试按 ## 切
    sections = re.split(r"\n(?=## )", doc.content)
    if len(sections) <= 1:
        # 无标题结构，按段落切
        paragraphs = doc.content.split("\n\n")
        current = ""
        for para in paragraphs:
            if len(current) + len(para) + 2 <= max_size:
                current += ("\n\n" + para) if current else para
            else:
                if current.strip():
                    chunks.append(Document(
                        content=current.strip(),
                        metadata={**doc.metadata, "heading": _extract_heading(doc.content[:100])}
                    ))
                current = para
        if current.strip():
            chunks.append(Document(
                content=current.strip(),
                metadata={**doc.metadata, "heading": _extract_heading(doc.content[:100])}
            ))
        return chunks

    for section in sections:
        if section.strip():
            chunks.append(Document(
                content=section.strip(),
                metadata={**doc.metadata, "heading": _extract_heading(section)}
            ))
    return chunks


def chunk_document(doc: Document, content_type: str, max_size: int = 800) -> List[Document]:
    """根据内容类型选择分块策略"""
    if content_type == "brief":
        return chunk_brief(doc, max_size=max_size)
    else:
        return chunk_article(doc, max_size=max_size)
