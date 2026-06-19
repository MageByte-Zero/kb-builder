#!/usr/bin/env python3
"""KB Builder — 索引管道：加载 Markdown → 分块 → embedding → Chroma"""

import os
import re
import sys
from pathlib import Path
from typing import List, Dict
from dataclasses import dataclass, field

import yaml

# 显式跳过的隐藏目录
_SKIP_DIRS = {".git", ".github", "node_modules", "__pycache__", ".venv", ".idea"}


@dataclass
class Document:
    """一个文档块，携带内容和元数据"""
    content: str
    metadata: Dict[str, str] = field(default_factory=dict)


class ConfigError(Exception):
    """配置错误"""
    pass


def load_config(config_path: str = "config.yaml") -> dict:
    """加载 config.yaml。配置不存在时抛出 ConfigError"""
    config_file = Path(config_path)
    if not config_file.exists():
        raise ConfigError(
            f"配置文件不存在: {config_path}\n"
            "请先编辑 config.yaml 声明你的内容源路径"
        )
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
        # 跳过显式指定的隐藏/无关目录
        parts_set = set(md_file.parts)
        if parts_set & _SKIP_DIRS:
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


def _chunk_text_by_size(text: str, heading: str, doc_meta: dict,
                        max_size: int) -> List[Document]:
    """将文本按 max_size 硬切。优先按段落边界切，单段超限时按句子切。"""
    chunks = []
    paragraphs = text.split("\n\n")
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 <= max_size:
            current += ("\n\n" + para) if current else para
            continue

        # 当前段落放不下，先保存 accumulated
        if current.strip():
            chunks.append(Document(
                content=current.strip(),
                metadata={**doc_meta, "heading": heading}
            ))
            current = ""

        # 如果单个段落超过 max_size，按句号切
        if len(para) > max_size:
            sentences = re.split(r"(?<=[。！？\.\!\?])\s*", para)
            for sent in sentences:
                if not sent.strip():
                    continue
                if len(current) + len(sent) <= max_size:
                    current += sent if not current else sent
                else:
                    if current.strip():
                        chunks.append(Document(
                            content=current.strip(),
                            metadata={**doc_meta, "heading": heading}
                        ))
                    # 单句仍超限则强制截断
                    if len(sent) > max_size:
                        for i in range(0, len(sent), max_size):
                            piece = sent[i:i + max_size].strip()
                            if piece:
                                chunks.append(Document(
                                    content=piece,
                                    metadata={**doc_meta, "heading": heading}
                                ))
                        current = ""
                    else:
                        current = sent
        else:
            current = para

    if current.strip():
        chunks.append(Document(
            content=current.strip(),
            metadata={**doc_meta, "heading": heading}
        ))
    return chunks


def chunk_article(doc: Document, max_size: int = 800) -> List[Document]:
    """策略 A：结构感知分块。按 ## 标题切，超限按 ### / #### / 段落逐级拆"""
    chunks = []
    sections = re.split(r"\n(?=## )", doc.content)

    for section in sections:
        if not section.strip():
            continue
        section_heading = _extract_heading(section)

        if len(section) <= max_size:
            chunks.append(Document(
                content=section.strip(),
                metadata={**doc.metadata, "heading": section_heading}
            ))
            continue

        # 按 ### 继续拆
        subs = re.split(r"\n(?=### )", section)
        for sub in subs:
            if not sub.strip():
                continue
            sub_heading = _extract_heading(sub)
            # 保留父级标题上下文
            full_heading = (
                f"{section_heading} > {sub_heading}"
                if section_heading and sub_heading
                else (section_heading or sub_heading)
            )

            if len(sub) <= max_size:
                chunks.append(Document(
                    content=sub.strip(),
                    metadata={**doc.metadata, "heading": full_heading}
                ))
                continue

            # 按 #### 继续拆
            deep_subs = re.split(r"\n(?=#### )", sub)
            if len(deep_subs) > 1:
                for ds in deep_subs:
                    if not ds.strip():
                        continue
                    ds_heading = _extract_heading(ds)
                    deep_full_heading = (
                        f"{full_heading} > {ds_heading}"
                        if full_heading and ds_heading
                        else (full_heading or ds_heading)
                    )
                    if len(ds) <= max_size:
                        chunks.append(Document(
                            content=ds.strip(),
                            metadata={**doc.metadata, "heading": deep_full_heading}
                        ))
                    else:
                        chunks.extend(_chunk_text_by_size(
                            ds, deep_full_heading, doc.metadata, max_size
                        ))
            else:
                chunks.extend(_chunk_text_by_size(
                    sub, full_heading, doc.metadata, max_size
                ))
    return chunks


def chunk_brief(doc: Document, max_size: int = 600) -> List[Document]:
    """策略 B：固定模板 / 段落分块"""
    chunks = []
    sections = re.split(r"\n(?=## )", doc.content)

    if len(sections) <= 1:
        heading = _extract_heading(doc.content) or _extract_heading(doc.content[:200])
        chunks.extend(_chunk_text_by_size(doc.content, heading, doc.metadata, max_size))
        return chunks

    for section in sections:
        if not section.strip():
            continue
        section_heading = _extract_heading(section)
        if len(section) <= max_size:
            chunks.append(Document(
                content=section.strip(),
                metadata={**doc.metadata, "heading": section_heading}
            ))
        else:
            chunks.extend(_chunk_text_by_size(
                section, section_heading, doc.metadata, max_size
            ))
    return chunks


def chunk_document(doc: Document, content_type: str, max_size: int = 800) -> List[Document]:
    """根据内容类型选择分块策略"""
    if content_type == "brief":
        return chunk_brief(doc, max_size=max_size)
    else:
        return chunk_article(doc, max_size=max_size)
