// result.js
document.addEventListener('click', (e) => {
  if (e.target.matches('.jump')) {
    const t = parseFloat(e.target.dataset.jump);
    // -> hier: player.currentTime = t; player.play();
  }
  if (e.target.matches('.copy')) {
    const id = e.target.dataset.id;
    const el = document.getElementById(id).querySelector('[data-text]');
    navigator.clipboard.writeText(el.textContent.trim()).then(() => {
      e.target.textContent = '✓ Kopiert';
      setTimeout(() => (e.target.textContent = '⧉ Kopieren'), 1200);
    });
  }
  if (e.target.matches('#copyAll')) {
    const all = [...document.querySelectorAll('.segment [data-text]')]
      .map(n => n.textContent.trim()).join('\n\n');
    navigator.clipboard.writeText(all);
  }
});

const search = document.getElementById('search');
const clearBtn = document.getElementById('clearSearch');

function clearHighlights() {
  document.querySelectorAll('.segment .text mark').forEach(m => {
    const parent = m.parentNode;
    parent.replaceChild(document.createTextNode(m.textContent), m);
    parent.normalize();
  });
}

function highlight(term) {
  if (!term) return;
  const re = new RegExp(`(${term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`,'gi');
  document.querySelectorAll('.segment .text').forEach(p => {
    const txt = p.textContent;
    p.innerHTML = txt.replace(re, '<mark>$1</mark>');
  });
}

search?.addEventListener('input', () => {
  clearHighlights();
  const q = search.value.trim();
  if (q.length >= 2) highlight(q);
});

clearBtn?.addEventListener('click', () => {
  search.value = '';
  clearHighlights();
  search.focus();
});

// Tastatur-Shortcuts (Enter = nächstes Ergebnis, Esc = löschen)
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') { clearBtn.click(); }
  if (e.key === 'Enter' && search.value.trim().length >= 2) {
    const marks = [...document.querySelectorAll('mark')];
    if (marks.length) {
      const next = marks.find(m => m.getBoundingClientRect().top > 0) || marks[0];
      next.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }
});
