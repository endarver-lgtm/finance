let expChart = null;
let incChart = null;

function initDashboardCharts() {
  if (!window.chartData || typeof Chart === 'undefined' || !window.financeCharts) return;

  const exp = document.getElementById('expenseChart');
  if (exp && window.chartData.expense && window.chartData.expense.labels && window.chartData.expense.labels.length) {
    if (expChart) {
      expChart.destroy();
      expChart = null;
    }
    if (window.chartData.expense.values.some((v) => v > 0)) {
      expChart = window.financeCharts.bar(exp, window.chartData.expense.labels, window.chartData.expense.values);
    } else {
      const note = document.createElement('div');
      note.className = 'chart-empty-note';
      note.textContent = 'За период ещё нет расходов';
      const box = exp.closest('.chart-box');
      if (box) box.replaceWith(note);
    }
  }

  const inc = document.getElementById('incomeChart');
  if (inc && window.chartData.income && window.chartData.income.labels) {
    if (incChart) {
      incChart.destroy();
      incChart = null;
    }
    incChart = window.financeCharts.line(
      inc,
      window.chartData.income.labels,
      window.chartData.income.plan,
      window.chartData.income.fact
    );
  }
}

window.initDashboardCharts = initDashboardCharts;

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initDashboardCharts);
} else {
  initDashboardCharts();
}
