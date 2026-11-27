'use strict';

const state = { zones: [], zone: null, cross: false, q: '' };

const $ = function (id) { return document.getElementById(id); };

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

function renderZones() {
  const box = $('zones');
  box.innerHTML = '';
  state.zones.forEach(function (zone) {
    const div = document.createElement('div');
    div.className = 'zone' + (zone.id === state.zone ? ' active' : '') + (zone.documents ? '' : ' empty-zone');
    div.innerHTML = '<span class="name">' + esc(zone.name) + '</span>'
      + '<span class="count">' + zone.documents + ' 篇</span>';
    if (zone.missing && zone.missing.length) {
      const warn = document.createElement('span');
      warn.className = 'warn';
      warn.textContent = '缺目录: ' + zone.missing.join(' ');
      div.appendChild(warn);
    }
    div.title = zone.purpose || '';
    div.addEventListener('click', function () {
      state.zone = zone.id;
      renderZones();
      if (state.q) runSearch();
      else renderEmpty();
    });
    box.appendChild(div);
  });
  const docs = state.zones.reduce(function (a, z) { return a + z.documents; }, 0);
  const chunks = state.zones.reduce(function (a, z) { return a + z.chunks; }, 0);
  $('meta').textContent = state.zones.length + ' 个分区 · ' + docs + ' 篇 · ' + chunks + ' 块';
}

function renderEmpty() {
  const el = $('empty');
  const docs = state.zones.reduce(function (a, z) { return a + z.documents; }, 0);
  if (docs > 0) {
    el.hidden = true;
    return;
  }
  const paths = [];
  state.zones.forEach(function (z) {
    (z.sources || []).forEach(function (s) { paths.push(s); });
  });
  el.hidden = false;
  el.innerHTML = '<h3>还没有任何文档</h3>'
    + '<div>把文件放进下面这些目录（支持 .md / .txt / .pdf / .docx），然后点右上角「重新索引」：</div>'
    + '<ul>' + paths.map(function (p) { return '<li><code>' + esc(p) + '</code></li>'; }).join('') + '</ul>'
    + '<div style="margin-top:8px">分区和目录的对应关系写在 <code>zones.toml</code> 里，改完重启服务即可。</div>';
}

function renderHits(data) {
  const list = $('hits');
  list.innerHTML = '';
  const el = $('empty');
  if (!data.hits.length) {
    el.hidden = false;
    el.innerHTML = '<h3>没有命中任何证据</h3><div>换个说法，或关掉日期过滤 / 打开跨区再试。</div>';
    setStatus('0 条结果 · ' + data.query);
    return;
  }
  el.hidden = true;
  data.hits.forEach(function (hit, i) {
    const li = document.createElement('li');
    li.className = 'hit';
    const path = hit.heading_path && hit.heading_path.length
      ? hit.source + ' # ' + hit.heading_path.join(' > ')
      : hit.source;
    li.innerHTML = '<div class="row1">'
      + '<span class="score">' + (i + 1) + ' · ' + hit.score.toFixed(3) + '</span>'
      + '<span class="zone-tag">' + esc(hit.zone_name) + '</span>'
      + '<span>' + esc(hit.date || '') + '</span>'
      + '</div>'
      + '<div class="title">' + esc(hit.title || '（无标题）') + '</div>'
      + '<div class="path">' + esc(path) + '</div>'
      + '<div class="snippet">' + mark(snippet(hit.text, data.query), data.query) + '</div>';
    li.addEventListener('click', function () { openDoc(hit.zone, hit.doc_id); });
    list.appendChild(li);
  });
  setStatus(data.hits.length + ' 条结果 · 跨区' + (state.cross ? '开' : '关'));
}

async function runSearch() {
  const q = $('q').value.trim();
  state.q = q;
  if (!q) {
    $('hits').innerHTML = '';
    renderEmpty();
    return;
  }
  const params = new URLSearchParams();
  params.set('q', q);
  params.set('k', '8');
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
      + '<pre>' + mark(doc.text.slice(0, 6000), state.q) + '</pre>';
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
  renderEmpty();
}

async function reindex() {
  setStatus('重新索引…');
  try {
    const data = await api('/api/reindex', { method: 'POST' });
    state.zones = data.zones;
    renderZones();
    renderEmpty();
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
$('closeDrawer').addEventListener('click', function () { $('drawer').hidden = true; });
document.addEventListener('keydown', function (ev) {
  if (ev.key === 'Escape') $('drawer').hidden = true;
});

loadZones().catch(function (err) { setStatus(err.message, true); });
