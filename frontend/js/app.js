/**
 * SocTrack Main App Logic
 * Handles UI state, rendering, and user interactions.
 *
 * Dependencies: api.js, charts.js, Chart.js
 */

// ── State ───────────────────────────────────────────────

let state = {
  brands: [],
  currentBrandId: null,
  currentPostId: null,
  posts: [],
  selectedCompare: new Set(),
  activeCharts: {},
};

// ── Init ────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
  try {
    state.brands = await api.getBrands();
    if (state.brands.length > 0) {
      selectBrand(state.brands[0].id);
    }
    renderBrandSidebar();
  } catch (e) {
    console.error('Failed to initialize:', e);
    // Fallback: show empty state
    renderBrandSidebar();
  }
});

// ── Navigation ──────────────────────────────────────────

function switchPage(page) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.getElementById(`page-${page}`)?.classList.add('active');
  document.querySelectorAll('.nav-item[data-page]').forEach(n =>
    n.classList.toggle('active', n.dataset.page === page)
  );
}

// ── Brand Sidebar ───────────────────────────────────────

function renderBrandSidebar() {
  const ownList = document.getElementById('brandList');
  const compList = document.getElementById('competitorList');
  if (!ownList || !compList) return;

  ownList.innerHTML = '';
  compList.innerHTML = '';

  state.brands.forEach(b => {
    const el = document.createElement('div');
    el.className = `brand-item ${b.id === state.currentBrandId ? 'active' : ''}`;
    el.onclick = () => selectBrand(b.id);
    el.innerHTML = `
      <span class="brand-emoji">${b.logo_emoji || '📦'}</span>
      <span class="brand-name">${b.name}</span>
      <span class="brand-badge ${b.is_competitor ? 'badge-comp' : 'badge-own'}">
        ${b.is_competitor ? 'COMP' : 'OWN'}
      </span>
    `;
    (b.is_competitor ? compList : ownList).appendChild(el);
  });
}

async function selectBrand(brandId) {
  state.currentBrandId = brandId;
  state.currentPostId = null;

  const brand = state.brands.find(b => b.id === brandId);
  const titleEl = document.getElementById('topbarTitle');
  if (titleEl) titleEl.textContent = `Dashboard — ${brand?.name || ''}`;

  renderBrandSidebar();

  try {
    state.posts = await api.getPostsByBrand(brandId);
    renderBrandStats();
    renderPostList();
    if (state.posts.length > 0) {
      selectPost(state.posts[0].id);
    }
  } catch (e) {
    console.error('Failed to load brand data:', e);
  }

  switchPage('dashboard');
}

// ── Brand Stats ─────────────────────────────────────────

async function renderBrandStats() {
  const grid = document.getElementById('brandStatsGrid');
  if (!grid) return;

  try {
    const stats = await api.getBrandStats(state.currentBrandId);
    grid.innerHTML = [
      { label: 'Views', value: stats.total_views, delta: stats.delta_views },
      { label: 'Likes', value: stats.total_likes, delta: stats.delta_likes },
      { label: 'Comments', value: stats.total_comments, delta: stats.delta_comments },
      { label: 'Shares', value: stats.total_shares, delta: stats.delta_shares },
    ].map(s => `
      <div class="stat-mini">
        <div class="stat-mini-label">${s.label}</div>
        <div class="stat-mini-value">${formatChartNum(s.value)}</div>
        <div class="stat-mini-delta ${s.delta >= 0 ? 'delta-up' : 'delta-down'}">
          ${s.delta >= 0 ? '+' : ''}${formatChartNum(s.delta)} today
        </div>
      </div>
    `).join('');
  } catch (e) {
    console.error('Failed to render brand stats:', e);
  }
}

// ── Post List ───────────────────────────────────────────

function renderPostList() {
  const container = document.getElementById('postListScroll');
  if (!container) return;

  container.innerHTML = state.posts.map(p => `
    <div class="post-row ${state.currentPostId === p.id ? 'active' : ''}"
         onclick="selectPost('${p.id}')">
      <input type="checkbox" class="post-checkbox"
        ${state.selectedCompare.has(p.id) ? 'checked' : ''}
        onclick="event.stopPropagation(); toggleCompare('${p.id}', this.checked)">
      <div class="post-thumb">▶</div>
      <div class="post-info">
        <div class="post-title">${p.title || 'Untitled'}</div>
        <div class="post-meta">${p.posted_at?.slice(0, 10) || ''} · via ${p.source}</div>
      </div>
    </div>
  `).join('');
}

async function selectPost(postId) {
  state.currentPostId = postId;
  renderPostList();

  try {
    const snapshots = await api.getSnapshots(postId);
    renderPostDetail(postId, snapshots);
  } catch (e) {
    console.error('Failed to load post detail:', e);
  }
}

// ── Post Detail ─────────────────────────────────────────

function renderPostDetail(postId, snapshots) {
  const post = state.posts.find(p => p.id === postId);
  const panel = document.getElementById('detailPanel');
  if (!post || !panel) return;

  // Build detail HTML (similar to the standalone dashboard)
  panel.innerHTML = `
    <div class="detail-header">
      <div class="detail-platform">TikTok</div>
      <div class="detail-title">${post.title || 'Untitled'}</div>
      <div class="detail-url">${post.tiktok_url}</div>
      <div class="detail-date">Tracking since ${post.tracking_since?.slice(0, 10) || 'N/A'}</div>
    </div>
    <div class="charts-grid">
      <div class="chart-box">
        <div class="chart-box-title">Daily Views</div>
        <div class="chart-container"><canvas id="chartViews"></canvas></div>
      </div>
      <div class="chart-box">
        <div class="chart-box-title">Daily Likes</div>
        <div class="chart-container"><canvas id="chartLikes"></canvas></div>
      </div>
    </div>
  `;

  // Render charts if we have snapshot data
  if (snapshots.length > 0) {
    const labels = snapshots.map(s => s.recorded_at?.slice(5, 10) || '');
    Object.values(state.activeCharts).forEach(c => c.destroy());
    state.activeCharts = {};

    const viewsCanvas = document.getElementById('chartViews');
    const likesCanvas = document.getElementById('chartLikes');

    if (viewsCanvas) {
      state.activeCharts.views = createDailyGainChart(
        viewsCanvas, labels, calculateDeltas(snapshots, 'views'), CHART_COLORS.views
      );
    }
    if (likesCanvas) {
      state.activeCharts.likes = createDailyGainChart(
        likesCanvas, labels, calculateDeltas(snapshots, 'likes'), CHART_COLORS.likes
      );
    }
  }
}

// ── Compare ─────────────────────────────────────────────

function toggleCompare(postId, checked) {
  if (checked) {
    state.selectedCompare.add(postId);
  } else {
    state.selectedCompare.delete(postId);
  }

  const bar = document.getElementById('compareBar');
  const count = state.selectedCompare.size;
  document.getElementById('compareCount').textContent = count;
  bar?.classList.toggle('show', count >= 2);
}

function goToCompare() {
  switchPage('compare');
}

// ── Modal ───────────────────────────────────────────────

function openModal() {
  document.getElementById('modalOverlay')?.classList.add('active');
}

function closeModal(e) {
  if (!e || e.target === e.currentTarget) {
    document.getElementById('modalOverlay')?.classList.remove('active');
  }
}

function switchModalTab(index, el) {
  document.querySelectorAll('.modal-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.modal-tab-content').forEach(t => t.classList.remove('active'));
  el.classList.add('active');
  document.getElementById(`modalTab${index}`)?.classList.add('active');
}

// ── Toast ───────────────────────────────────────────────

function showToast(msg) {
  const t = document.getElementById('toast');
  if (!t) return;
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2500);
}
