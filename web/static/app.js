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
    showSourcePanel: false,
    managedSources: [],
    newSource: { name: '', type: '', url: '' },

    // Lifecycle
    async init() {
      await Promise.all([
        this.loadTopics(),
        this.loadStats(),
        this.loadManagedSources()
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
    },

    // Source management
    async loadManagedSources() {
      try {
        const res = await fetch('/api/sources');
        if (res.ok) {
          const data = await res.json();
          this.managedSources = data.sources || [];
        }
      } catch (e) {
        console.error('Failed to load sources:', e);
      }
    },

    async addSource() {
      const { name, type, url } = this.newSource;
      if (!name || !type || !url) return;

      try {
        const res = await fetch('/api/sources', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, type, url })
        });
        if (res.ok) {
          this.newSource = { name: '', type: '', url: '' };
          await this.loadManagedSources();
          this.pollSourceStatus();
        } else {
          const err = await res.json();
          alert(err.error || '添加失败');
        }
      } catch (e) {
        alert('网络错误: ' + e.message);
      }
    },

    async deleteSource(id, name) {
      if (!confirm(`确认删除「${name}」？本地文件也会被删除。`)) return;
      try {
        const res = await fetch(`/api/sources/${id}`, { method: 'DELETE' });
        if (res.ok) await this.loadManagedSources();
      } catch (e) {
        alert('删除失败: ' + e.message);
      }
    },

    async syncSource(id) {
      try {
        const res = await fetch(`/api/sources/${id}/sync`, { method: 'POST' });
        if (res.ok) {
          await this.loadManagedSources();
          this.pollSourceStatus();
        }
      } catch (e) {
        alert('同步失败: ' + e.message);
      }
    },

    async toggleSource(id) {
      try {
        const res = await fetch(`/api/sources/${id}/toggle`, { method: 'PUT' });
        if (res.ok) await this.loadManagedSources();
      } catch (e) {
        alert('操作失败: ' + e.message);
      }
    },

    pollSourceStatus() {
      const poll = setInterval(async () => {
        await this.loadManagedSources();
        const hasActive = this.managedSources.some(
          s => s.status === 'syncing' || s.status === 'indexing'
        );
        if (!hasActive) {
          clearInterval(poll);
          this.loadTopics();
          this.loadStats();
        }
      }, 3000);
    },

    statusText(src) {
      const map = { pending: '等待中', syncing: '同步中...', indexing: '索引中...', ready: '就绪', error: '错误' };
      return map[src.status] || src.status;
    },

    timeAgo(iso) {
      if (!iso) return '';
      const diff = Date.now() - new Date(iso).getTime();
      const mins = Math.floor(diff / 60000);
      if (mins < 1) return '刚刚';
      if (mins < 60) return mins + ' 分钟前';
      const hours = Math.floor(mins / 60);
      if (hours < 24) return hours + ' 小时前';
      return Math.floor(hours / 24) + ' 天前';
    }
  }));
});
