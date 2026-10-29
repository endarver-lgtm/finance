document.addEventListener('DOMContentLoaded', () => {
  if (!window.chartData || typeof Chart === 'undefined' || !window.financeCharts) return;

  const exp = document.getElementById('expenseChart');
  if (exp && window.chartData.expense.labels.length) {
    if (window.chartData.expense.values.some((v) => v > 0)) {
      window.financeCharts.bar(exp, window.chartData.expense.labels, window.chartData.expense.values);
    } else {
      const note = document.createElement('div');
      note.className = 'chart-empty-note';
      note.textContent = 'За период ещё нет расходов';
      exp.closest('.chart-box').replaceWith(note);
    }
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
