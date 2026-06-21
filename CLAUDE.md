# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

KB Builder is a Python tool that indexes Markdown documents into a ChromaDB vector store and exposes semantic search via MCP (Model Context Protocol) for Claude Code. It also has a FastAPI web UI for browser-based search.

## Commands

All scripts live in `scripts/` and expect `config.yaml` in the same directory. The virtual environment is at `.venv/`.

```bash
# Activate venv first
source .venv/bin/activate

# Index content into ChromaDB (incremental)
cd scripts && python index.py index

# Full rebuild (clears existing collection first)
cd scripts && python index.py index --full

# CLI search for testing retrieval quality
cd scripts && python search.py "你的查询" [--top-k 8] [--type article|brief] [--source name]

# View index stats / topic distribution
cd scripts && python index.py stats
cd scripts && python index.py topics

# Run Web UI (FastAPI + Alpine.js)
python web.py [--port 8000] [--config scripts/config.yaml]
```

First-time setup: `cd scripts && bash install.sh` (creates venv, installs deps, optionally clones content source, registers MCP server with Claude Code).

## Architecture

Three entry points share the same core indexer:

1. **`scripts/index.py`** — CLI indexer. Contains `RAGIndexer` class (ChromaDB init, index, search, stats) and all chunking logic. This is the single source of truth for indexing and retrieval.
2. **`mcp/kb_server.py`** — MCP server (FastMCP, stdio transport). Imports `RAGIndexer` from `scripts/index.py` via `sys.path` manipulation. Exposes `search_kb`, `list_kb_topics`, `get_kb_stats` as MCP tools. Runs as a singleton process; lazy-loads the indexer on first call.
3. **`web/app.py`** — FastAPI web app. Also imports `RAGIndexer` from `scripts/index.py`. Serves a Jinja2/Alpine.js frontend. Entry point is `web.py` (project root) which launches uvicorn.

### Data Flow

```
config.yaml → load_config() → RAGIndexer.__init__()
                                    ↓
                    ChromaDB PersistentClient (./chroma_db/)
                    + SentenceTransformer embedding (paraphrase-multilingual-MiniLM-L12-v2)
                                    ↓
Markdown files → load_markdown_files() → chunk_document() → collection.upsert()
```

### Chunking Strategies

- **Article** (`chunk_article`): Structure-aware — splits by `##` → `###` → `####` headings, falls back to paragraph/sentence splitting. Default max 800 chars.
- **Brief** (`chunk_brief`): Simpler — splits by `##` sections, then paragraph/sentence. Default max 600 chars.
- Content type is auto-detected from directory name (`articles/` → article, `briefs/` → brief).

### Key Config (`scripts/config.yaml`)

- `content_sources[].path` — absolute path to Markdown directory
- `content_sources[].enabled` — toggle without removing
- `index.embedding_model` — HuggingFace model name (default: `paraphrase-multilingual-MiniLM-L12-v2`)
- `chunking.article_max_size` / `brief_max_size` — max chars per chunk
- `index.persist_dir` — ChromaDB storage path (relative to scripts/)

### MCP Registration

The install script registers the MCP server via `claude mcp add` (user scope). The `KB_CONFIG_PATH` env var points the MCP server to the correct config. MCP transport is stdio.

## Key Conventions

- All paths in config.yaml are absolute or `~`-expanded.
- Chunk IDs are MD5 hashes of `{source_name}:{source_path}:{index}`.
- The `sys.path.insert(0, ...)` pattern is used to share `scripts/index.py` across all three entry points — there is no package installation.
- ChromaDB metadata values are truncated to 512 chars; heading to 256 chars; topic to 128 chars.
- Embedding uses cosine similarity (`hnsw:space: cosine`).
