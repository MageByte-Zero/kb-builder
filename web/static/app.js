document.addEventListener('alpine:init', () => {
  Alpine.data('kbApp', () => ({
    // State
    query: '',
    contentType: '',
    sourceFilter: '',
    results: [],
    topics: [],
    stats: null,
    sources: [],
    loading: false,
    searched: false,
    articleView: false,
    articleContent: '',
    articleTitle: '',
    sidebarOpen: false,

    // Lifecycle
    async init() {
      await Promise.all([
        this.loadTopics(),
        this.loadStats()
      ]);
    },

    // API calls
    async loadTopics() {
      try {
        const res = await fetch('/api/topics');
        if (res.ok) {
          const data = await res.json();
          this.topics = data.topics || data || [];
        }
      } catch (e) {
        console.error('Failed to load topics:', e);
      }
    },

    async loadStats() {
      try {
        const res = await fetch('/api/stats');
        if (res.ok) {
          this.stats = await res.json();
          if (this.stats && this.stats.sources) {
            this.sources = this.stats.sources;
          }
        }
      } catch (e) {
        console.error('Failed to load stats:', e);
      }
    },

    async doSearch() {
      const q = this.query.trim();
      if (!q) return;

      this.loading = true;
      this.searched = true;
      this.articleView = false;
      this.results = [];

      try {
        const params = new URLSearchParams({
          q,
          top_k: '10',
          content_type: this.contentType || 'all',
          source: this.sourceFilter || 'all'
        });

        const res = await fetch(`/api/search?${params}`);
        if (res.ok) {
          const data = await res.json();
          this.results = (data.results || data || []).map(item => ({
            ...item,
            // API returns relevance_pct as number (e.g. 85.2), convert to 0-1 score for display
            score: (item.relevance_pct || 0) / 100,
            path: item.source_path || item.source || item.path || '',
            snippet: item.content || item.snippet || '',
            source_name: item.source_name || item.source || ''
          }));
        } else {
          console.error('Search failed:', res.status);
        }
      } catch (e) {
        console.error('Search error:', e);
      } finally {
        this.loading = false;
      }
    },

    async viewArticle(path) {
      if (!path) return;
      this.loading = true;
      this.articleView = true;

      try {
        const res = await fetch(`/api/article?path=${encodeURIComponent(path)}`);
        if (res.ok) {
          const data = await res.json();
          this.articleTitle = data.title || '';
          this.articleContent = data.content || '';
          // Render markdown after DOM update
          this.$nextTick(() => {
            this.renderMarkdown();
          });
        }
      } catch (e) {
        console.error('Failed to load article:', e);
      } finally {
        this.loading = false;
      }
    },

    renderMarkdown() {
      const el = document.getElementById('article-body');
      if (el && window.marked) {
        el.innerHTML = marked.parse(this.articleContent, {
          breaks: true,
          gfm: true,
          highlight: function(code, lang) {
            if (window.hljs && lang && hljs.getLanguage(lang)) {
              return hljs.highlight(code, { language: lang }).value;
            }
            return code;
          }
        });
        // Apply highlight.js to code blocks
        if (window.hljs) {
          el.querySelectorAll('pre code').forEach((block) => {
            hljs.highlightElement(block);
          });
        }
      }
    },

    backToResults() {
      this.articleView = false;
      this.articleContent = '';
      this.articleTitle = '';
    },

    topicDisplayName(topic) {
      const key = topic.key || topic.name || topic.topic || '';
      // "backend/redis" → "redis", "wechat-ai/claude-code" → "claude-code"
      const parts = key.split('/');
      return parts[parts.length - 1] || key;
    },

    clickTopic(topic) {
      // Use the last segment of the key as the search query
      this.query = this.topicDisplayName(topic);
      this.doSearch();
      this.closeSidebar();
    },

    selectSource(source) {
      this.sourceFilter = source;
      if (this.searched) this.doSearch();
    },

    applySuggestion(text) {
      this.query = text;
      this.doSearch();
    },

    closeSidebar() {
      this.sidebarOpen = false;
    },

    toggleSidebar() {
      this.sidebarOpen = !this.sidebarOpen;
    },

    // Helpers
    relevanceClass(score) {
      // score is 0-1 (converted from relevance_pct)
      if (score >= 0.85) return 'relevance-high';
      if (score >= 0.70) return 'relevance-mid';
      return 'relevance-low';
    },

    relevancePercent(score) {
      // score is already 0-1, display as percentage
      return Math.round(score * 100) + '%';
    },

    animDelay(index) {
      return `animation-delay: ${index * 50}ms`;
    }
  }));
});
