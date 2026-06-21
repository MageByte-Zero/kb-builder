#!/usr/bin/env python3
"""KB Builder — 索引管道：加载 Markdown → 分块 → embedding → Chroma"""

import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import List, Dict
from dataclasses import dataclass, field

import chromadb
import yaml
from chromadb.utils import embedding_functions

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


# ── RAGIndexer ──────────────────────────────────────────────


class RAGIndexer:
    """管理 Chroma 向量库：初始化、索引、检索"""

    def __init__(self, config: dict):
        self.config = config
        idx_cfg = config["index"]

        persist_dir = os.path.expanduser(idx_cfg["persist_dir"])
        os.makedirs(persist_dir, exist_ok=True)

        model_name = idx_cfg.get("embedding_model", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
        device = idx_cfg.get("device", "cpu")

        try:
            self.embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=model_name,
                device=device,
                normalize_embeddings=True,
            )
        except Exception as e:
            raise RuntimeError(
                f"无法加载 embedding 模型 '{model_name}'。\n"
                f"请检查网络连接（首次需从 HuggingFace 下载 ~500MB），"
                f"或尝试设置 HF_ENDPOINT=https://hf-mirror.com\n"
                f"原始错误: {e}"
            )

        try:
            self.client = chromadb.PersistentClient(path=persist_dir)
        except Exception as e:
            raise RuntimeError(
                f"无法打开 Chroma 数据库: {persist_dir}\n"
                f"请检查路径权限和磁盘空间。\n原始错误: {e}"
            )

        self.collection_name = idx_cfg.get("collection_name", "unified_kb")

        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=self.embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )

    def index_documents(self, chunks: List[Document], source_name: str, content_type: str):
        """批量写入 chunks 到 Chroma"""
        if not chunks:
            return 0

        ids = []
        documents = []
        metadatas = []

        for i, c in enumerate(chunks):
            uniq = f"{source_name}:{c.metadata.get('source_path', '')}:{i}"
            chunk_id = hashlib.md5(uniq.encode()).hexdigest()
            ids.append(chunk_id)
            documents.append(c.content)
            meta = {
                "source_path": c.metadata.get("source_path", "")[:512],
                "source_name": source_name,
                "content_type": content_type,
                "topic": c.metadata.get("topic", "")[:128],
                "heading": c.metadata.get("heading", "")[:256],
                "file_name": c.metadata.get("file_name", "")[:256],
                "file_mtime": c.metadata.get("file_mtime", ""),
                "word_count": str(len(c.content)),
            }
            metadatas.append({k: str(v)[:512] for k, v in meta.items()})

        batch_size = 100
        total = 0
        for i in range(0, len(ids), batch_size):
            end = min(i + batch_size, len(ids))
            self.collection.upsert(
                ids=ids[i:end],
                documents=documents[i:end],
                metadatas=metadatas[i:end],
            )
            total += (end - i)
        return total

    def get_merged_sources(self, source_manager=None) -> list:
        """合并 sources.json 和 config.yaml 中的来源（去重）"""
        sources = list(self.config.get("content_sources", []))

        if source_manager is None:
            try:
                from sources.manager import SourceManager
                source_manager = SourceManager()
            except ImportError:
                return sources

        for src in source_manager.list():
            if not src.enabled or src.status != "ready":
                continue
            # 去重：检查 local_path 是否已在 config 中
            if any(s.get("path") == src.local_path for s in sources):
                continue
            sources.append({
                "name": src.name,
                "path": src.local_path,
                "enabled": True,
            })

        return sources

    def index_all(self, full: bool = False):
        """遍历所有来源（config + sources.json），执行索引。
        full=True 时先清空 collection 再重建。"""
        sources = self.get_merged_sources()
        if not sources:
            print("[ERROR] config.yaml 中未声明任何 content_sources")
            return None

        # 全量重建：删除旧 collection 再创建
        if full:
            print("[INFO] 全量重建模式 — 清空现有索引...")
            try:
                self.client.delete_collection(self.collection_name)
            except Exception:
                pass  # collection 可能不存在
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=self.embedding_fn,
                metadata={"hnsw:space": "cosine"},
            )

        chunking = self.config.get("chunking", {})
        article_max = chunking.get("article_max_size", 800)
        brief_max = chunking.get("brief_max_size", 600)

        total_files = 0
        total_chunks = 0

        for source in sources:
            if not source.get("enabled", False):
                print(f"[SKIP] {source['name']} (disabled)")
                continue

            path = os.path.expanduser(source["path"])
            name = source["name"]
            print(f"\n{'='*60}")
            print(f"[索引] {name} ← {path}")
            print(f"{'='*60}")

            docs = load_markdown_files(path)
            print(f"  扫描到 {len(docs)} 个 .md 文件")

            content_type = _determine_content_type(path)
            max_size = brief_max if content_type == "brief" else article_max

            all_chunks = []
            for doc in docs:
                chunks = chunk_document(doc, content_type, max_size=max_size)
                all_chunks.extend(chunks)

            print(f"  分块完成：{len(docs)} 篇文档 → {len(all_chunks)} chunks")

            written = self.index_documents(all_chunks, name, content_type)
            print(f"  写入 Chroma：{written} chunks")

            total_files += len(docs)
            total_chunks += len(all_chunks)

        print(f"\n{'='*60}")
        print(f"[完成] 总计：{total_files} 篇文档 → {total_chunks} chunks")
        print(f"  Collection: {self.collection_name}")
        print(f"  Total vectors: {self.collection.count()}")
        print(f"{'='*60}")

        return {"total_files": total_files, "total_chunks": total_chunks}

    def search(self, query: str, top_k: int = 5,
               content_type: str = "all", source: str = "all") -> List[dict]:
        """检索，支持按 content_type 和 source 过滤"""
        where_filter = None
        conditions = []
        if content_type and content_type != "all":
            conditions.append({"content_type": content_type})
        if source and source != "all":
            conditions.append({"source_name": source})

        if len(conditions) == 1:
            where_filter = conditions[0]
        elif len(conditions) > 1:
            where_filter = {"$and": conditions}

        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=top_k,
                where=where_filter,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as e:
            print(f"[WARN] 检索出错: {e}")
            return []

        hits = []
        if not results.get("ids") or not results["ids"][0]:
            return hits

        for i in range(len(results["ids"][0])):
            meta = results["metadatas"][0][i] if results.get("metadatas") and results["metadatas"][0] else {}
            hits.append({
                "content": results["documents"][0][i] if results.get("documents") and results["documents"][0] else "",
                "source": meta.get("source_path", ""),
                "source_name": meta.get("source_name", ""),
                "content_type": meta.get("content_type", ""),
                "heading": meta.get("heading", ""),
                "topic": meta.get("topic", ""),
                "distance": results["distances"][0][i] if results.get("distances") and results["distances"][0] else 1.0,
            })
        return hits

    def get_topics(self, limit: int = 5000) -> List[dict]:
        """统计各 topic 的 chunk 分布（采样前 limit 条，默认 5000）"""
        all_meta = self.collection.get(include=["metadatas"], limit=limit)
        topic_counts = {}
        for m in all_meta.get("metadatas", []):
            if m:
                topic = m.get("topic", "unknown")
                source = m.get("source_name", "unknown")
                key = f"{source}/{topic}"
                topic_counts[key] = topic_counts.get(key, 0) + 1
        return [{"key": k, "count": v} for k, v in sorted(
            topic_counts.items(), key=lambda x: -x[1])]

    def get_stats(self) -> dict:
        """返回索引统计"""
        return {
            "collection": self.collection_name,
            "total_vectors": self.collection.count(),
            "sources": self.config.get("content_sources", []),
        }


# ── CLI Entry Point ────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="KB Builder — 知识库索引工具")
    sub = parser.add_subparsers(dest="command")

    idx_parser = sub.add_parser("index", help="索引内容到向量库")
    idx_parser.add_argument("--config", default="config.yaml", help="配置文件路径")
    idx_parser.add_argument("--full", action="store_true", help="全量重建索引")

    search_parser = sub.add_parser("search", help="命令行检索")
    search_parser.add_argument("query", help="检索查询")
    search_parser.add_argument("--config", default="config.yaml", help="配置文件路径")
    search_parser.add_argument("--top-k", type=int, default=5)
    search_parser.add_argument("--type", default="all", help="内容类型过滤")
    search_parser.add_argument("--source", default="all", help="来源过滤")

    stats_parser = sub.add_parser("stats", help="查看索引状态")
    stats_parser.add_argument("--config", default="config.yaml", help="配置文件路径")

    topics_parser = sub.add_parser("topics", help="列出所有主题")
    topics_parser.add_argument("--config", default="config.yaml", help="配置文件路径")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # load_config raises ConfigError if config missing
    try:
        config = load_config(args.config)
    except ConfigError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    os.chdir(Path(args.config).parent)

    if args.command == "index":
        indexer = RAGIndexer(config)
        indexer.index_all(full=args.full)

    elif args.command == "search":
        indexer = RAGIndexer(config)
        hits = indexer.search(args.query, top_k=args.top_k,
                              content_type=args.type, source=args.source)
        if not hits:
            print("未找到相关结果。")
            return
        print(f"\n📖 查询: {args.query}\n")
        print(f"📝 Top-{len(hits)} 结果:\n")
        for i, h in enumerate(hits, 1):
            relevance = max(0, 1 - h["distance"])
            print(f"[{i}] {h['source']} > {h.get('heading', '')} "
                  f"(相关度: {relevance:.1%})")
            print(f"    {h['content'][:200]}...\n")

    elif args.command == "stats":
        indexer = RAGIndexer(config)
        stats = indexer.get_stats()
        print(f"Collection: {stats['collection']}")
        print(f"Total vectors: {stats['total_vectors']}")

    elif args.command == "topics":
        indexer = RAGIndexer(config)
        topics = indexer.get_topics()
        print(f"\n📚 知识库主题分布:\n")
        for t in topics:
            print(f"  {t['key']}: {t['count']} chunks")


if __name__ == "__main__":
    main()
