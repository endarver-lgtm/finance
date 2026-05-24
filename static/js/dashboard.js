document.addEventListener('DOMContentLoaded', () => {
  if (!window.chartData || typeof Chart === 'undefined' || !window.financeCharts) return;

  const exp = document.getElementById('expenseChart');
  if (exp && window.chartData.expense.labels.length) {
    window.financeCharts.bar(exp, window.chartData.expense.labels, window.chartData.expense.values);
  }

  const inc = document.getElementById('incomeChart');
  if (inc) {
    window.financeCharts.line(
      inc,
      window.chartData.income.labels,
      window.chartData.income.plan,
      window.chartData.income.fact
    );
  }
});
