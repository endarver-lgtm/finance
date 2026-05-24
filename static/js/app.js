(function () {
  function openModal(id) {
    const el = document.getElementById(id);
    if (el) {
      el.classList.add('open');
      el.setAttribute('aria-hidden', 'false');
    }
  }

  function closeModal(el) {
    el.classList.remove('open');
    el.setAttribute('aria-hidden', 'true');
  }

  function closeAll() {
    document.querySelectorAll('.modal.open').forEach(closeModal);
  }

  document.addEventListener('click', (e) => {
    const openBtn = e.target.closest('[data-open]');
    if (openBtn) {
      e.preventDefault();
      openModal(openBtn.getAttribute('data-open'));
      return;
    }
    if (e.target.closest('[data-close]')) {
      const modal = e.target.closest('.modal');
      if (modal) closeModal(modal);
      else closeAll();
    }
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeAll();
  });

  const chartDefaults = () => {
    if (typeof Chart === 'undefined') return;
    Chart.defaults.font.family = "'Inter', sans-serif";
    Chart.defaults.color = '#6b7280';
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', chartDefaults);
  } else {
    chartDefaults();
  }

  function moneyLabel(value) {
    const rate = window.FINANCE?.usdRate || 3.27;
    const byn = Number(value) || 0;
    const usd = byn / rate;
    return `${byn.toFixed(2)} BYN (≈ $${usd.toFixed(2)})`;
  }

  window.financeCharts = {
    bar(ctx, labels, values) {
      return new Chart(ctx, {
        type: 'bar',
        data: {
          labels,
          datasets: [{
            data: values,
            backgroundColor: labels.map((_, i) =>
              i === values.indexOf(Math.max(...values)) ? '#4ADE80' : '#D1D5DB'
            ),
            borderRadius: 8,
            borderSkipped: false,
          }],
        },
        options: {
          responsive: true,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (ctx) => moneyLabel(ctx.parsed.y),
              },
            },
          },
          scales: {
            y: {
              beginAtZero: true,
              grid: { color: '#f5f5f5' },
              ticks: {
                callback: (v) => `${v} BYN`,
              },
            },
            x: { grid: { display: false } },
          },
        },
      });
    },
    line(ctx, labels, plan, fact) {
      return new Chart(ctx, {
        type: 'line',
        data: {
          labels,
          datasets: [
            {
              label: 'План',
              data: plan,
              borderColor: '#9CA3AF',
              backgroundColor: 'transparent',
              tension: 0.35,
              borderDash: [4, 4],
            },
            {
              label: 'Факт',
              data: fact,
              borderColor: '#4ADE80',
              backgroundColor: 'rgba(74, 222, 128, 0.15)',
              fill: true,
              tension: 0.35,
            },
          ],
        },
        options: {
          responsive: true,
          plugins: {
            legend: { position: 'bottom' },
            tooltip: {
              callbacks: {
                label: (ctx) => `${ctx.dataset.label}: ${moneyLabel(ctx.parsed.y)}`,
              },
            },
          },
          scales: {
            y: {
              beginAtZero: true,
              grid: { color: '#f5f5f5' },
              ticks: {
                callback: (v) => `${v} BYN`,
              },
            },
            x: { grid: { display: false } },
          },
        },
      });
    },
  };
})();
