/**
 * SocTrack Chart.js Configurations
 * Reusable chart factories for the dashboard.
 */

// ── Global Chart.js Defaults ────────────────────────────

Chart.defaults.color = '#9090b0';
Chart.defaults.font.family = "'Inter', -apple-system, BlinkMacSystemFont, sans-serif";
Chart.defaults.font.size = 11;

// ── Color Palette ───────────────────────────────────────

const CHART_COLORS = {
  views: '#8B5CF6',
  likes: '#ef4444',
  comments: '#3b82f6',
  shares: '#22c55e',
  accent: '#8B5CF6',
};

// ── Helpers ─────────────────────────────────────────────

function formatChartNum(n) {
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
  return n.toString();
}

/**
 * Calculate daily deltas from cumulative snapshot data.
 * @param {Array} snapshots - Array of snapshot objects with metric values
 * @param {string} key - Metric key (views, likes, comments, shares)
 * @returns {Array} Array of delta values
 */
function calculateDeltas(snapshots, key) {
  return snapshots.map((s, i) =>
    i === 0 ? 0 : s[key] - snapshots[i - 1][key]
  );
}

// ── Chart Factories ─────────────────────────────────────

/**
 * Create a daily gain bar chart.
 * @param {HTMLCanvasElement} canvas
 * @param {Array} labels - Date labels
 * @param {Array} data - Delta values
 * @param {string} color - Hex color
 * @returns {Chart} Chart.js instance
 */
function createDailyGainChart(canvas, labels, data, color) {
  return new Chart(canvas, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        data,
        backgroundColor: color + '88',
        borderColor: color,
        borderWidth: 1,
        borderRadius: 3,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: {
          grid: { display: false },
          ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 7 },
        },
        y: {
          grid: { color: 'rgba(42,42,66,0.5)' },
          ticks: { callback: v => formatChartNum(v) },
        },
      },
    },
  });
}

/**
 * Create a cumulative trend line chart (for compare view).
 * @param {HTMLCanvasElement} canvas
 * @param {Array} labels - Date labels
 * @param {Array} data - Cumulative values
 * @param {string} color - Hex color
 * @returns {Chart} Chart.js instance
 */
function createTrendChart(canvas, labels, data, color) {
  return new Chart(canvas, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        data,
        borderColor: color,
        backgroundColor: color + '22',
        fill: true,
        tension: 0.3,
        pointRadius: 0,
        borderWidth: 2,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { display: false },
        y: {
          grid: { color: 'rgba(42,42,66,0.3)' },
          ticks: { callback: v => formatChartNum(v) },
        },
      },
    },
  });
}

/**
 * Create a multi-dataset comparison chart.
 * @param {HTMLCanvasElement} canvas
 * @param {Array} labels - Date labels
 * @param {Array} datasets - Array of { label, data, color }
 * @returns {Chart} Chart.js instance
 */
function createComparisonChart(canvas, labels, datasets) {
  return new Chart(canvas, {
    type: 'line',
    data: {
      labels,
      datasets: datasets.map(ds => ({
        label: ds.label,
        data: ds.data,
        borderColor: ds.color,
        backgroundColor: ds.color + '22',
        fill: false,
        tension: 0.3,
        pointRadius: 2,
        borderWidth: 2,
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'top',
          labels: { boxWidth: 12, padding: 16 },
        },
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 7 },
        },
        y: {
          grid: { color: 'rgba(42,42,66,0.3)' },
          ticks: { callback: v => formatChartNum(v) },
        },
      },
    },
  });
}
