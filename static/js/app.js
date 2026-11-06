(function () {
  function openModal(id) {
    const el = document.getElementById(id);
    if (el) {
      // Teleport modal directly to document.body so it is never trapped by any ancestor container, transform or table cell
      if (el.parentElement !== document.body) {
        document.body.appendChild(el);
      }
      el.classList.add('open');
      el.setAttribute('aria-hidden', 'false');
      document.body.classList.add('modal-open');

      // Ensure modal container and dialog are at the top of the active viewport
      el.scrollTop = 0;
      const dialog = el.querySelector('.modal-dialog');
      if (dialog) dialog.scrollTop = 0;
    }
  }

  function closeModal(el) {
    el.classList.remove('open');
    el.setAttribute('aria-hidden', 'true');
    if (!document.querySelector('.modal.open')) {
      document.body.classList.remove('modal-open');
    }
  }

  function closeAll() {
    document.querySelectorAll('.modal.open').forEach(closeModal);
    document.body.classList.remove('modal-open');
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
    Chart.defaults.font.family = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
    Chart.defaults.font.size = 12;
    Chart.defaults.color = '#5e554a';
    Chart.defaults.maintainAspectRatio = false;
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', chartDefaults);
  } else {
    chartDefaults();
  }

  function moneyLabel(valueByn) {
    const rate = window.FINANCE?.usdRate || 3.27;
    const byn = Number(valueByn) || 0;
    const usd = byn / rate;
    return `${byn.toFixed(2)} BYN (≈ $${usd.toFixed(2)})`;
  }

  window.financeCharts = {
    bar(ctx, labels, values) {
      const maxVal = Math.max(...values);
      return new Chart(ctx, {
        type: 'bar',
        data: {
          labels,
          datasets: [{
            data: values,
            backgroundColor: values.map((v) =>
              v === maxVal && v > 0 ? '#1b5e3f' : '#dfd8cc'
            ),
            hoverBackgroundColor: values.map((v) =>
              v === maxVal && v > 0 ? '#154c32' : '#cfc7ba'
            ),
            borderRadius: 6,
            borderSkipped: false,
          }],
        },
        options: {
          responsive: true,
          plugins: {
            legend: { display: false },
            tooltip: {
              backgroundColor: '#1f1b16',
              titleColor: '#efe9de',
              bodyColor: '#efe9de',
              padding: 10,
              cornerRadius: 6,
              displayColors: false,
              callbacks: {
                label: (ctx) => moneyLabel(ctx.parsed.y),
              },
            },
          },
          scales: {
            y: {
              beginAtZero: true,
              grid: { color: 'rgba(31, 27, 22, 0.06)' },
              ticks: {
                font: { family: "'JetBrains Mono', monospace", size: 11 },
                callback: (v) => `${v} BYN`,
              },
            },
            x: {
              grid: { display: false },
              ticks: { font: { size: 12 } }
            },
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
              borderColor: '#8a847a',
              backgroundColor: 'transparent',
              tension: 0.25,
              borderWidth: 1.5,
              borderDash: [4, 4],
              pointRadius: 3,
              pointBackgroundColor: '#8a847a',
            },
            {
              label: 'Факт',
              data: fact,
              borderColor: '#1b5e3f',
              backgroundColor: 'rgba(27, 94, 63, 0.07)',
              fill: true,
              tension: 0.25,
              borderWidth: 2,
              pointRadius: 4,
              pointBackgroundColor: '#1b5e3f',
            },
          ],
        },
        options: {
          responsive: true,
          plugins: {
            legend: {
              position: 'bottom',
              labels: {
                boxWidth: 12,
                boxHeight: 12,
                padding: 16,
                usePointStyle: true,
              }
            },
            tooltip: {
              backgroundColor: '#1f1b16',
              titleColor: '#efe9de',
              bodyColor: '#efe9de',
              padding: 10,
              cornerRadius: 6,
              callbacks: {
                label: (ctx) => `${ctx.dataset.label}: ${moneyLabel(ctx.parsed.y)}`,
              },
            },
          },
          scales: {
            y: {
              beginAtZero: true,
              grid: { color: 'rgba(31, 27, 22, 0.06)' },
              ticks: {
                font: { family: "'JetBrains Mono', monospace", size: 11 },
                callback: (v) => `${v} BYN`,
              },
            },
            x: {
              grid: { display: false },
              ticks: { font: { size: 12 } }
            },
          },
        },
      });
    },
  };

  /* --------------------------------------------------------------------------
     Modern Flat SaaS View Transitions (Buttery Smooth & Tactile)
     -------------------------------------------------------------------------- */
  let isNavigating = false;
  let progressBar = null;

  function getProgressBar() {
    if (!progressBar) {
      progressBar = document.createElement('div');
      progressBar.className = 'saas-nav-progress';
      document.body.appendChild(progressBar);
    }
    return progressBar;
  }

  function startProgress() {
    const bar = getProgressBar();
    bar.classList.remove('done');
    bar.classList.add('loading');
  }

  function finishProgress() {
    const bar = getProgressBar();
    bar.classList.add('done');
    setTimeout(() => {
      bar.classList.remove('loading', 'done');
    }, 280);
  }

  function updateActiveNav(targetUrl) {
    const targetPath = new URL(targetUrl, window.location.origin).pathname;
    document.querySelectorAll('.nav-item, .bottom-nav-item, .more-nav-item').forEach((item) => {
      const itemUrl = item.getAttribute('href');
      if (!itemUrl) return;
      const itemPath = new URL(itemUrl, window.location.origin).pathname;
      if (itemPath === targetPath) {
        item.classList.add('active');
      } else {
        item.classList.remove('active');
      }
    });

    // Also update "Ещё" modal trigger state in bottom nav
    const moreBtn = document.querySelector('.bottom-nav-item[data-open="modal-more-nav"]');
    if (moreBtn) {
      const morePrefixes = ['/debts', '/balance', '/history', '/settings'];
      if (morePrefixes.some((p) => targetPath.startsWith(p))) {
        moreBtn.classList.add('active');
      } else {
        moreBtn.classList.remove('active');
      }
    }
  }

  async function navigateTo(url, push = true) {
    if (isNavigating) return;
    isNavigating = true;

    // Instantly close any open modals (e.g. mobile "Ещё" sheet)
    closeAll();

    // Tactile haptic response on devices that support it
    if (window.navigator?.vibrate) {
      try { window.navigator.vibrate(10); } catch (_) {}
    }

    // Immediately update active navigation indicator (0ms tactile feedback)
    updateActiveNav(url);
    startProgress();

    try {
      const resp = await fetch(url, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const htmlText = await resp.text();
      const parser = new DOMParser();
      const doc = parser.parseFromString(htmlText, 'text/html');

      const newMain = doc.querySelector('.main');
      const currentMain = document.querySelector('.main');

      if (!newMain || !currentMain) {
        window.location.href = url;
        return;
      }

      const applyNewContent = () => {
        // Clean up any previously teleported modals from earlier pages
        document.querySelectorAll('body > .modal:not(#modal-more-nav)').forEach((m) => {
          m.remove();
        });

        document.title = doc.title;
        currentMain.innerHTML = newMain.innerHTML;
        updateActiveNav(url);
        if (push) {
          window.history.pushState({ url }, doc.title, url);
        }
        window.scrollTo({ top: 0, behavior: 'instant' });

        // Execute any script tags in the new content
        doc.querySelectorAll('script').forEach((oldScript) => {
          const src = oldScript.getAttribute('src');
          if (src && (src.includes('chart') || src.includes('app.js'))) {
            return;
          }
          const newScript = document.createElement('script');
          Array.from(oldScript.attributes).forEach((attr) => {
            newScript.setAttribute(attr.name, attr.value);
          });
          newScript.textContent = oldScript.textContent;
          document.body.appendChild(newScript);
          newScript.remove();
        });

        // Re-run dashboard charts if dashboard initialized
        if (window.initDashboardCharts) {
          window.initDashboardCharts();
        }
      };

      if (document.startViewTransition) {
        await document.startViewTransition(() => {
          applyNewContent();
        }).finished;
      } else {
        currentMain.classList.add('page-exit');
        await new Promise((r) => setTimeout(r, 140));
        applyNewContent();
        currentMain.classList.remove('page-exit');
        currentMain.classList.add('page-enter');
        setTimeout(() => currentMain.classList.remove('page-enter'), 280);
      }
    } catch (err) {
      console.warn('Navigation fallback:', err);
      window.location.href = url;
    } finally {
      finishProgress();
      isNavigating = false;
    }
  }

  window.navigateTo = navigateTo;

  // Intercept navigation clicks across the application
  document.addEventListener('click', (e) => {
    const link = e.target.closest('a');
    if (!link) return;

    const href = link.getAttribute('href');
    if (!href || href.startsWith('#') || href.startsWith('javascript:') || href.startsWith('mailto:') || href.startsWith('tel:')) return;
    if (link.getAttribute('target') === '_blank' || link.hasAttribute('download')) return;

    let url;
    try {
      url = new URL(link.href, window.location.origin);
    } catch (_) {
      return;
    }
    if (url.origin !== window.location.origin) return;

    // Check if link is a nav item, period button, card link, brand logo, or internal action link
    const isNav = link.closest(
      '.nav-item, .bottom-nav-item, .more-nav-item, .period-btn, .card-link, .rates-widget-link, .mobile-rate-chip, .mobile-topbar-brand, .month-nav a, .btn-sm[href], .btn[href], a.text-link[href^="/"]'
    );
    if (!isNav) return;

    e.preventDefault();
    navigateTo(link.href, true);
  });

  window.addEventListener('popstate', () => {
    navigateTo(window.location.href, false);
  });
})();
