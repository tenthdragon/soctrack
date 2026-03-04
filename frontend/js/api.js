/**
 * SocTrack API Client
 * Handles all communication with FastAPI backend.
 */

const API_BASE = '/api';

const api = {
  // ── Brands ──────────────────────────────────────────

  async getBrands() {
    const res = await fetch(`${API_BASE}/brands`);
    return res.json();
  },

  async createBrand(data) {
    const res = await fetch(`${API_BASE}/brands`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return res.json();
  },

  async updateBrand(id, data) {
    const res = await fetch(`${API_BASE}/brands/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return res.json();
  },

  async deleteBrand(id) {
    return fetch(`${API_BASE}/brands/${id}`, { method: 'DELETE' });
  },

  // ── Posts ───────────────────────────────────────────

  async getPostsByBrand(brandId) {
    const res = await fetch(`${API_BASE}/brands/${brandId}/posts`);
    return res.json();
  },

  async addPostByLink(data) {
    const res = await fetch(`${API_BASE}/posts/add-by-link`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return res.json();
  },

  async addPostByAccount(data) {
    const res = await fetch(`${API_BASE}/posts/add-by-account`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return res.json();
  },

  async updatePost(id, data) {
    const res = await fetch(`${API_BASE}/posts/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return res.json();
  },

  async deletePost(id) {
    return fetch(`${API_BASE}/posts/${id}`, { method: 'DELETE' });
  },

  // ── Snapshots & Metrics ─────────────────────────────

  async getSnapshots(postId, dateFrom, dateTo) {
    const params = new URLSearchParams();
    if (dateFrom) params.set('date_from', dateFrom);
    if (dateTo) params.set('date_to', dateTo);
    const res = await fetch(`${API_BASE}/posts/${postId}/snapshots?${params}`);
    return res.json();
  },

  async getBrandStats(brandId) {
    const res = await fetch(`${API_BASE}/brands/${brandId}/stats`);
    return res.json();
  },

  async getBrandDailyStats(brandId, days = 14) {
    const res = await fetch(`${API_BASE}/brands/${brandId}/stats/daily?days=${days}`);
    return res.json();
  },

  async comparePosts(postIds) {
    const ids = postIds.join(',');
    const res = await fetch(`${API_BASE}/compare?post_ids=${ids}`);
    return res.json();
  },

  // ── Discovery ───────────────────────────────────────

  async searchDiscovery(keyword, maxResults = 50) {
    const res = await fetch(`${API_BASE}/discovery/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keyword, max_results: maxResults }),
    });
    return res.json();
  },

  async getDiscoveryResults(keyword, isTracked) {
    const params = new URLSearchParams();
    if (keyword) params.set('keyword', keyword);
    if (isTracked !== undefined) params.set('is_tracked', isTracked);
    const res = await fetch(`${API_BASE}/discovery/results?${params}`);
    return res.json();
  },

  async trackDiscoveryResult(resultId, brandId) {
    const res = await fetch(`${API_BASE}/discovery/track/${resultId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ brand_id: brandId }),
    });
    return res.json();
  },

  // ── Health ──────────────────────────────────────────

  async healthCheck() {
    const res = await fetch(`${API_BASE}/health`);
    return res.json();
  },
};
