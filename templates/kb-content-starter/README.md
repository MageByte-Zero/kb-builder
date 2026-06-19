# 我的知识库内容源

这是你的知识库内容目录。按以下结构组织 Markdown 文件：

```
├── articles/       ← 原创长文（专栏、博客）
├── briefs/         ← 信息摘要（论文解读、工具测评、行业动态）
│   ├── papers/
│   ├── tools/
│   └── trends/
├── community/      ← 社区精华（可选）
└── glossary.md     ← 术语表（提高检索精度）
```

## 使用

1. 将你的 Markdown 文件按类型放入对应目录
2. 在 kb-builder 的 config.yaml 中添加此目录为内容源
3. 运行 `python index.py index` 建立索引
4. 在 Claude Code 中开始检索

## 内容建议

- 每篇文章建议有 frontmatter 元数据（keywords、audience 等），提高检索精度
- 文章标题用 Markdown 标题层级（##/###），有助于自动分块
- 短摘要（briefs/）控制在 300-1000 字
