#!/usr/bin/env python3
"""KB Builder — 命令行快速检索验证"""

import os
import sys
from pathlib import Path

# 确保能 import 同目录下的 index 模块
sys.path.insert(0, str(Path(__file__).parent))

from index import load_config, ConfigError, RAGIndexer


def main():
    if len(sys.argv) < 2:
        print("用法: python search.py <查询内容> [--top-k N] [--type article|brief|all] [--source name]")
        print("示例: python search.py 'Redis 集群分片设计' --top-k 8")
        sys.exit(1)

    query = sys.argv[1]
    top_k = 5
    content_type = "all"
    source = "all"

    # 简单参数解析
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--top-k" and i + 1 < len(args):
            top_k = int(args[i + 1])
            i += 2
        elif args[i] == "--type" and i + 1 < len(args):
            content_type = args[i + 1]
            i += 2
        elif args[i] == "--source" and i + 1 < len(args):
            source = args[i + 1]
            i += 2
        else:
            print(f"[WARN] 未知参数: {args[i]}")
            i += 1

    # 加载配置
    script_dir = Path(__file__).parent
    config_path = script_dir / "config.yaml"
    os.chdir(script_dir)

    try:
        config = load_config(str(config_path))
    except ConfigError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    indexer = RAGIndexer(config)

    # 检索
    hits = indexer.search(query, top_k=top_k, content_type=content_type, source=source)

    if not hits:
        print("\n❌ 未在知识库中找到相关结果。")
        print("建议:")
        print("  1. 试试更宽泛的查询词")
        print("  2. 用 python index.py topics 看看有哪些主题")
        print("  3. 确认内容源已在 config.yaml 中启用且已索引")
        return

    print(f"\n📖 查询: {query}")
    print(f"📝 Top-{len(hits)} 结果 (content_type={content_type}, source={source}):\n")
    print("=" * 70)

    for i, h in enumerate(hits, 1):
        relevance = max(0, 1 - h["distance"])
        bar = "█" * int(relevance * 20)
        topic_tag = f" [{h.get('topic', '')}]" if h.get('topic') else ""
        print(f"\n[{i}] {h['source']}{topic_tag}")
        print(f"    {h.get('heading', '')}")
        print(f"    相关度: {relevance:.1%} {bar}")
        print(f"    ---")
        # 显示前 300 字符
        preview = h["content"][:300].replace("\n", " ")
        print(f"    {preview}...")
        print()

    print("=" * 70)


if __name__ == "__main__":
    main()
