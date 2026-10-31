// DROPZONE 公開サイトの小さな動き
document.documentElement.classList.add('js');

// ニュースのカテゴリ絞り込み
document.querySelectorAll('.filters').forEach((box) => {
  const list = box.parentElement.querySelector('[data-filter-list]');
  if (!list) return;
  box.addEventListener('click', (e) => {
    const b = e.target.closest('.fbtn'); if (!b) return;
    box.querySelectorAll('.fbtn').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    const f = b.dataset.f;
    list.querySelectorAll('[data-cat]').forEach((r) => { r.hidden = f !== 'all' && r.dataset.cat !== f; });
  });
});

// 大会ページのステージ切り替え
document.querySelectorAll('.tabs').forEach((tabs) => {
  const panels = [...tabs.parentElement.querySelectorAll('[data-panel]')];
  const show = (id) => {
    tabs.querySelectorAll('.tab').forEach((t) => t.setAttribute('aria-selected', String(t.dataset.tab === id)));
    panels.forEach((p) => { p.hidden = p.id !== id; });
  };
  tabs.addEventListener('click', (e) => { const t = e.target.closest('.tab'); if (t) show(t.dataset.tab); });
  if (panels[0]) show(panels[0].id);
});

// 選手一覧の絞り込み
document.querySelectorAll('[data-filter-table]').forEach((inp) => {
  const tb = document.getElementById(inp.dataset.filterTable)?.tBodies[0];
  inp.addEventListener('input', () => {
    const q = inp.value.trim().toLowerCase();
    [...(tb?.rows || [])].forEach((r) => { r.hidden = q && !r.textContent.toLowerCase().includes(q); });
  });
});

// サイト内検索
(async () => {
  const box = document.getElementById('sr');
  if (!box) return;
  const q = new URLSearchParams(location.search).get('q') || '';
  const inp = document.getElementById('q'); if (inp) inp.value = q;
  if (!q.trim()) return;
  try {
    const idx = await (await fetch('/search.json')).json();
    const words = q.toLowerCase().split(/\s+/).filter(Boolean);
    const hit = idx.filter((x) => words.every((w) => x.k.toLowerCase().includes(w))).slice(0, 100);
    const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    box.innerHTML = hit.length
      ? hit.map((x) => `<a class="nrow" href="${esc(x.u)}"><span class="badge">${esc(x.t)}</span><span class="ntitle">${esc(x.n)}</span></a>`).join('')
      : `<p class="mut pad">「${esc(q)}」に一致する結果はありませんでした。</p>`;
  } catch { box.innerHTML = '<p class="mut pad">検索データを読み込めませんでした。</p>'; }
})();
