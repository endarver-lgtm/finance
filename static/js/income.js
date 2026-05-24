document.addEventListener('DOMContentLoaded', () => {
  const el = document.getElementById('incomePageChart');
  if (!el || !window.incomeChart || typeof Chart === 'undefined' || !window.financeCharts) return;
  window.financeCharts.line(
    el,
    window.incomeChart.labels,
    window.incomeChart.plan,
    window.incomeChart.fact
  );
});
