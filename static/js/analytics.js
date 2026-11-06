let trendsChart = null;
let paretoChart = null;

function initAnalyticsCharts() {
  if (!window.analyticsData || typeof Chart === 'undefined' || !window.financeCharts) return;

  // 1. 6-Month Trends Multi-Line Chart
  const trendsEl = document.getElementById('trendsChart');
  if (trendsEl && window.analyticsData.trends) {
    if (trendsChart) {
      trendsChart.destroy();
      trendsChart = null;
    }

    const t = window.analyticsData.trends;
    const datasets = [
      {
        label: 'Доходы',
        data: t.income,
        borderColor: '#1b5e3f',
        backgroundColor: 'rgba(27, 94, 63, 0.08)',
        fill: true,
        tension: 0.3,
        borderWidth: 2.5,
        pointRadius: 4,
        pointBackgroundColor: '#1b5e3f',
      },
      {
        label: 'Расходы',
        data: t.expense,
        borderColor: '#e07a5f',
        backgroundColor: 'transparent',
        tension: 0.3,
        borderWidth: 2,
        pointRadius: 4,
        pointBackgroundColor: '#e07a5f',
      },
      {
        label: 'Сбережения',
        data: t.savings,
        borderColor: '#3b82f6',
        backgroundColor: 'transparent',
        tension: 0.3,
        borderWidth: 1.8,
        borderDash: [5, 4],
        pointRadius: 3,
        pointBackgroundColor: '#3b82f6',
      },
    ];

    trendsChart = window.financeCharts.multiLine(trendsEl, t.labels, datasets);
  }

  // 2. AI refresh button listener
  const btnRefresh = document.getElementById('btnRefreshAi');
  const reviewContent = document.getElementById('aiReviewText');
  const reviewBadge = document.getElementById('aiReviewBadge');
  if (btnRefresh && reviewContent) {
    btnRefresh.addEventListener('click', async () => {
      const originalText = btnRefresh.innerHTML;
      btnRefresh.disabled = true;
      btnRefresh.innerHTML = '<span>Анализирую...</span>';
      try {
        const resp = await fetch('/analytics/refresh-ai', { method: 'POST' });
        const data = await resp.json();
        if (data.success && data.text) {
          reviewContent.innerHTML = data.text;
          if (reviewBadge && data.model) {
            reviewBadge.textContent = '✨ ' + data.model;
            reviewBadge.className = data.is_ai_live ? 'badge badge-ok' : 'badge badge-neutral';
          }
        }
      } catch (e) {
        console.error('Error refreshing AI audit:', e);
      } finally {
        btnRefresh.disabled = false;
        btnRefresh.innerHTML = originalText;
      }
    });
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initAnalyticsCharts);
} else {
  initAnalyticsCharts();
}
