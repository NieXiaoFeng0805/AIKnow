'use strict';

const state = { zones: [], zone: null, cross: false, q: '' };

const $ = function (id) { return document.getElementById(id); };

const PALETTE = ['#6ea8ff', '#b78bff', '#5fe0a8', '#ffb86b', '#ff8b8b', '#66d9e8'];
const FIXED = { life: '#5fe0a8', work: '#6ea8ff', study: '#b78bff', home: '#ffb86b' };

function accentOf(zoneId) {
  const idx = state.zones.findIndex(function (z) { return z.id === zoneId; });
  return FIXED[zoneId] || PALETTE[(idx < 0 ? 0 : idx) % PALETTE.length];
}

async function api(path, options) {
  const res = await fetch(path, options);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || ('HTTP ' + res.status));
  return data;
}

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function terms(q) {
  const out = [];
  q.split(/\s+/).forEach(function (t) {
    if (!t) return;
    out.push(t);
    if (/[\u4e00-\u9fff]/.test(t) && t.length > 2) {
      for (let i = 0; i < t.length - 1; i += 1) out.push(t.slice(i, i + 2));
    }
  });
  return Array.from(new Set(out)).sort(function (a, b) { return b.length - a.length; });
}

const RE_SPECIAL = /[.*+?^{}$()|[\]\\]/g;

function mark(text, q) {
  const html = esc(text);
  const ts = terms(q).filter(function (t) { return t.length > 0; });
  if (!ts.length) return html;
  const pattern = ts.map(function (t) { return esc(t).replace(RE_SPECIAL, '\\$&'); }).join('|');
  try {
    return html.replace(new RegExp('(' + pattern + ')', 'g'), '<mark>$1</mark>');
  } catch (err) {
    return html;
  }
}

function snippet(text, q) {
  const t = terms(q)[0] || '';
  const idx = t ? text.toLowerCase().indexOf(t.toLowerCase()) : -1;
  const start = idx > 120 ? idx - 100 : 0;
  const piece = text.slice(start, start + 280);
  return (start > 0 ? '…' : '') + piece + (start + 280 < text.length ? '…' : '');
}

function setStatus(text, isError) {
  const el = $('status');
  el.textContent = text || '';
  el.className = isError ? 'status error' : 'status';
}

function renderStats() {
  const docs = state.zones.reduce(function (a, z) { return a + z.documents; }, 0);
  const chunks = state.zones.reduce(function (a, z) { return a + z.chunks; }, 0);
  const rows = [
    ['分区', state.zones.length],
    ['文档', docs],
    ['切块', chunks]
  ];
  $('stats').innerHTML = rows.map(function (r) {
    return '<div class="chip"><i class="dot"></i><span>' + r[0] + '</span><b>' + r[1] + '</b></div>';
  }).join('');
  $('zoneCount').textContent = state.zones.length + ' 个';
  const names = state.zones.map(function (z) { return z.name; }).join(' / ');
  const tip = document.getElementById('heroTip');
  if (tip && names) tip.textContent = names + ' 隔离，检索默认不串区';
}

function renderZones() {
  const box = $('zones');
  box.innerHTML = '';
  state.zones.forEach(function (zone) {
    const div = document.createElement('div');
    div.className = 'zone' + (zone.id === state.zone ? ' active' : '') + (zone.documents ? '' : ' is-empty');
    div.style.setProperty('--accent', accentOf(zone.id));
    div.innerHTML = '<div class="zone-top">'
      + '<span class="zone-name">' + esc(zone.name) + '</span>'
      + '<span class="zone-count">' + zone.documents + ' 篇</span>'
      + '</div>'
      + '<div class="zone-purpose">' + esc(zone.purpose || (zone.sources || []).join(' · ')) + '</div>';
    if (zone.missing && zone.missing.length) {
      const warn = document.createElement('div');
      warn.className = 'zone-warn';
      warn.textContent = '缺目录: ' + zone.missing.join(' ');
      div.appendChild(warn);
    }
    div.title = (zone.sources || []).join(' · ');
    div.addEventListener('click', function () {
      state.zone = zone.id;
      renderZones();
      if (state.q) runSearch();
      else renderPlaceholder();
    });
    box.appendChild(div);
  });
  renderStats();
}

function renderPlaceholder() {
  const el = $('empty');
  const docs = state.zones.reduce(function (a, z) { return a + z.documents; }, 0);
  if (docs === 0) {
    const paths = [];
    state.zones.forEach(function (z) {
      (z.sources || []).forEach(function (s) { paths.push(s); });
    });
    el.hidden = false;
    el.innerHTML = '<h3>还没有任何文档</h3>'
      + '<div>把文件放进下面这些目录（.md / .txt / .pdf / .docx），然后点右上角「重新索引」：</div>'
      + '<ul>' + paths.map(function (p) { return '<li>' + esc(p) + '</li>'; }).join('') + '</ul>'
      + '<div class="hint">分区与目录的对应关系写在 zones.toml，改完重启服务即可。</div>';
    return;
  }
  if (state.q) return;
  const examples = ['分区是怎么划分的', '文档解析用了什么后端', '阶段 1 的验收清单'];
  const features = [
    ['分区隔离', '文档与切块都带 zone，检索必须带区，跨区要显式打开'],
    ['出处回链', '每条结果给出文件与章节路径，点开可读整篇原文'],
    ['只给证据', '命中片段高亮，不做生成式回答，不替你下结论']
  ];
  el.hidden = false;
  el.innerHTML = '<h3>输入一句话，从分区里捞证据</h3>'
    + '<div>结果只给原文片段和出处，不做生成式回答；点任意一条右侧展开整篇原文。</div>'
    + '<div class="examples">'
    + examples.map(function (q) { return '<button type="button" class="example">' + esc(q) + '</button>'; }).join('')
    + '</div>'
    + '<div class="hint">回车检索 · 按 / 聚焦搜索框 · Esc 关闭原文 · 跨区默认关闭</div>'
    + '<div class="features">'
    + features.map(function (f, i) {
      return '<div class="feature" style="--accent: ' + PALETTE[i % PALETTE.length] + '">'
        + '<div class="feature-name">' + f[0] + '</div>'
        + '<div class="feature-desc">' + f[1] + '</div>'
        + '</div>';
    }).join('')
    + '</div>';
  Array.prototype.forEach.call(el.querySelectorAll('.example'), function (btn) {
    btn.addEventListener('click', function () {
      $('q').value = btn.textContent;
      runSearch();
    });
  });
}

function renderHits(data) {
  const list = $('hits');
  list.innerHTML = '';
  const el = $('empty');
  if (!data.hits.length) {
    state.q = data.query;
    el.hidden = false;
    el.innerHTML = '<h3>没有命中任何证据</h3>'
      + '<div>换个说法，或去掉日期过滤、打开「跨区」再试一次。</div>';
    setStatus('0 条结果 · ' + data.query);
    return;
  }
  el.hidden = true;
  data.hits.forEach(function (hit, i) {
    const card = document.createElement('article');
    card.className = 'hit' + (hit.kind === 'table' ? ' is-table' : '');
    card.style.setProperty('--accent', accentOf(hit.zone));
    card.style.setProperty('--i', String(i));
    const path = hit.heading_path && hit.heading_path.length
      ? hit.source + '  ›  ' + hit.heading_path.join(' › ')
      : hit.source;
    card.innerHTML = '<div class="row1">'
      + '<span class="score">' + (i + 1) + ' · ' + hit.score.toFixed(3) + '</span>'
      + '<span class="zone-tag">' + esc(hit.zone_name) + '</span>'
      + '<span class="kind">' + esc(hit.kind === 'table' ? '表格' : '正文') + '</span>'
      + '<span>' + esc(hit.date || '') + '</span>'
      + '</div>'
      + '<div class="title">' + esc(hit.title || '（无标题）') + '</div>'
      + '<div class="path">' + esc(path) + '</div>'
      + '<div class="snippet">' + mark(snippet(hit.text, data.query), data.query) + '</div>';
    card.addEventListener('click', function () { openDoc(hit.zone, hit.doc_id); });
    list.appendChild(card);
  });
  setStatus(data.hits.length + ' 条结果 · 跨区' + (state.cross ? '开' : '关') + ' · ' + data.query);
}

async function runSearch() {
  const q = $('q').value.trim();
  state.q = q;
  if (!q) {
    $('hits').innerHTML = '';
    renderPlaceholder();
    return;
  }
  const params = new URLSearchParams();
  params.set('q', q);
  params.set('k', '12');
  if (state.cross) {
    params.set('zones', state.zones.map(function (z) { return z.id; }).join(','));
  } else if (state.zone) {
    params.set('zone', state.zone);
  }
  const since = $('since').value;
  if (since) params.set('since', since);
  setStatus('检索中…');
  try {
    renderHits(await api('/api/search?' + params.toString()));
  } catch (err) {
    setStatus(err.message, true);
  }
}

function closeDrawer() { $('drawer').hidden = true; }

async function openDoc(zone, docId) {
  const drawer = $('drawer');
  const body = $('drawerBody');
  body.innerHTML = '<div class="path">载入中…</div>';
  drawer.hidden = false;
  try {
    const doc = await api('/api/doc?zone=' + encodeURIComponent(zone) + '&doc_id=' + encodeURIComponent(docId));
    body.innerHTML = '<h2>' + esc(doc.title || '（无标题）') + '</h2>'
      + '<div class="path">' + esc(doc.path) + '</div>'
      + '<div class="path">' + esc(doc.zone + ' · ' + (doc.date || '') + ' · ' + (doc.backend || '')) + '</div>'
      + '<pre>' + mark(doc.text.slice(0, 8000), state.q) + '</pre>';
  } catch (err) {
    body.innerHTML = '<div class="status error">' + esc(err.message) + '</div>';
  }
}

async function loadZones() {
  state.zones = await api('/api/zones');
  const known = state.zones.some(function (z) { return z.id === state.zone; });
  if (!state.zone || !known) {
    const withDocs = state.zones.find(function (z) { return z.documents > 0; });
    state.zone = (withDocs || state.zones[0] || {}).id || null;
  }
  renderZones();
  renderPlaceholder();
}

async function reindex() {
  setStatus('重新索引…');
  try {
    const data = await api('/api/reindex', { method: 'POST' });
    state.zones = data.zones;
    renderZones();
    renderPlaceholder();
    setStatus('已索引 ' + data.documents + ' 篇 / ' + data.chunks + ' 块');
    if (state.q) runSearch();
  } catch (err) {
    setStatus(err.message, true);
  }
}

$('searchform').addEventListener('submit', function (ev) {
  ev.preventDefault();
  runSearch();
});
$('cross').addEventListener('change', function (ev) {
  state.cross = ev.target.checked;
  if (state.q) runSearch();
});
$('since').addEventListener('change', function () { if (state.q) runSearch(); });
$('reindex').addEventListener('click', reindex);
$('closeDrawer').addEventListener('click', closeDrawer);
$('drawerMask').addEventListener('click', closeDrawer);
document.addEventListener('keydown', function (ev) {
  if (ev.key === 'Escape') { closeDrawer(); return; }
  if (ev.key === '/' && document.activeElement !== $('q')) {
    ev.preventDefault();
    $('q').focus();
  }
});

loadZones().catch(function (err) { setStatus(err.message, true); });
