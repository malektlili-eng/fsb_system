/* ================================================================
   FSB — Script Principal  |  static/js/fsb.js
   ================================================================ */

document.addEventListener('DOMContentLoaded', function () {

  /* ---- Active nav link ---- */
  const links = document.querySelectorAll('.sidebar-link');
  links.forEach(link => {
    if (link.href === window.location.href) {
      link.classList.add('active');
    }
  });

  /* ---- Auto-dismiss alerts ---- */
  document.querySelectorAll('.alert-fsb').forEach(alert => {
    setTimeout(() => {
      alert.style.transition = 'opacity 0.5s, transform 0.5s';
      alert.style.opacity = '0';
      alert.style.transform = 'translateY(-8px)';
      setTimeout(() => alert.remove(), 500);
    }, 4000);
  });

  /* ---- Table row hover highlight ---- */
  document.querySelectorAll('.table-fsb tbody tr').forEach(row => {
    row.style.cursor = 'pointer';
  });

  /* ---- Animate stat cards on load ---- */
  const stats = document.querySelectorAll('.stat-card');
  stats.forEach((card, i) => {
    card.style.animationDelay = `${i * 0.07}s`;
    card.classList.add('fu');
  });

  /* ---- Tooltip initialization (Bootstrap) ---- */
  if (typeof bootstrap !== 'undefined') {
    const tooltipEls = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    tooltipEls.forEach(el => new bootstrap.Tooltip(el));
  }

  /* ---- Confirm delete dialogs ---- */
  document.querySelectorAll('[data-confirm]').forEach(btn => {
    btn.addEventListener('click', function (e) {
      if (!confirm(this.dataset.confirm || 'Confirmer cette action ?')) {
        e.preventDefault();
      }
    });
  });

  /* ---- Mobile sidebar toggle ---- */
  const toggleBtn = document.getElementById('sidebarToggle');
  const sidebar   = document.getElementById('sidebar');
  if (toggleBtn && sidebar) {
    toggleBtn.addEventListener('click', () => sidebar.classList.toggle('open'));
    document.addEventListener('click', e => {
      if (sidebar.classList.contains('open') && !sidebar.contains(e.target) && e.target !== toggleBtn) {
        sidebar.classList.remove('open');
      }
    });
  }

  /* ---- Number counter animation ---- */
  function animateCount(el) {
    const target = parseInt(el.textContent, 10);
    if (isNaN(target)) return;
    let current = 0;
    const step = Math.ceil(target / 30);
    const timer = setInterval(() => {
      current = Math.min(current + step, target);
      el.textContent = current;
      if (current >= target) clearInterval(timer);
    }, 30);
  }
  document.querySelectorAll('.stat-num').forEach(el => animateCount(el));

});

/* ================================================================
   UTILITY FUNCTIONS (global)
   ================================================================ */

/** Show a toast notification */
function showToast(message, type = 'info') {
  const colors = {
    success: { bg: '#dcfce7', color: '#166534', icon: 'fa-check-circle' },
    error:   { bg: '#fee2e2', color: '#991b1b', icon: 'fa-exclamation-circle' },
    info:    { bg: '#dbeafe', color: '#1d4ed8', icon: 'fa-info-circle' },
    warning: { bg: '#fef9c3', color: '#854d0e', icon: 'fa-exclamation-triangle' },
  };
  const c = colors[type] || colors.info;
  const toast = document.createElement('div');
  toast.style.cssText = `
    position:fixed; top:18px; right:18px; z-index:9999;
    background:${c.bg}; color:${c.color};
    border-radius:10px; padding:12px 18px;
    font-size:0.875rem; font-weight:600;
    box-shadow:0 4px 20px rgba(0,0,0,0.12);
    display:flex; align-items:center; gap:8px;
    animation:fadeUp 0.3s ease;
    max-width:340px;
  `;
  toast.innerHTML = `<i class="fas ${c.icon}"></i> ${message}`;
  document.body.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.4s';
    setTimeout(() => toast.remove(), 400);
  }, 3500);
}

/** Format a date string to French locale */
function formatDate(dateStr) {
  if (!dateStr) return '—';
  const d = new Date(dateStr);
  return d.toLocaleDateString('fr-TN', { day: '2-digit', month: 'short', year: 'numeric' });
}

/** CSRF token helper for fetch() */
function getCsrf() {
  return document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
}