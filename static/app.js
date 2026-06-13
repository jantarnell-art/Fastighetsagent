'use strict';

const API = '/api';

const PROPERTY_TYPES = [
  'Handel',
  'Kontor',
  'Bostäder',
  'Industri/lager/logistik',
  'Samhällsfastigheter',
  'Hotell',
  'Mark/exploatering',
  'Blandfastigheter',
  'Övrigt',
];

const TYPE_BADGE_CLASS = {
  'Handel': 'badge-handel',
  'Kontor': 'badge-kontor',
  'Bostäder': 'badge-bostader',
  'Industri/lager/logistik': 'badge-industri',
  'Samhällsfastigheter': 'badge-samhalle',
  'Hotell': 'badge-hotell',
  'Mark/exploatering': 'badge-mark',
  'Blandfastigheter': 'badge-blandfastigheter',
  'Övrigt': 'badge-ovrigt',
};

const SAMPLE_JSON = [
  {
    buyer: "Castellum AB",
    seller: "Privat säljare AB",
    price_sek: 285000000,
    price_text: "285 MSEK",
    property_type: "Kontor",
    property_designation: "Stockholm Centrum 1:5",
    address: "Kungsgatan 10",
    municipality: "Stockholm",
    county: "Stockholm",
    transaction_date: "2025-03-15",
    access_date: "2025-06-01",
    source_name: "Fastighetsnytt",
    source_url: "https://fastighetsnytt.se/exempel",
    area_sqm: 12500,
    residential_units: null,
    tenants: "Deloitte (60%), SEB (40%)",
    yield_percent: 4.8,
    portfolio_flag: false,
    confidence_score: 0.9,
    raw_text: "Castellum förvärvar kontorsfastighet i centrala Stockholm med långa hyreskontrakt."
  }
];

let transactions = [];
let currentEditId = null;
let currentDetailId = null;
let sortCol = 'transaction_date';
let sortDir = 'desc';

let txModal, detailModal, importModal;

// ─── Init ─────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  txModal = new bootstrap.Modal(document.getElementById('txModal'));
  detailModal = new bootstrap.Modal(document.getElementById('detailModal'));
  importModal = new bootstrap.Modal(document.getElementById('importModal'));

  populatePropertySelects();

  document.getElementById('btn-add').addEventListener('click', openAddForm);
  document.getElementById('btn-search').addEventListener('click', loadTransactions);
  document.getElementById('btn-clear').addEventListener('click', clearFilters);
  document.getElementById('btn-export').addEventListener('click', exportCSV);
  document.getElementById('btn-import').addEventListener('click', () => importModal.show());
  document.getElementById('btn-sample').addEventListener('click', fillSample);
  document.getElementById('btn-do-import').addEventListener('click', doImport);
  document.getElementById('form-tx').addEventListener('submit', saveTx);
  document.getElementById('btn-edit-from-detail').addEventListener('click', editFromDetail);
  document.getElementById('btn-delete-from-detail').addEventListener('click', deleteFromDetail);
  document.getElementById('btn-summarize').addEventListener('click', generateSummary);

  document.querySelectorAll('#filter-panel input, #filter-panel select').forEach(el => {
    el.addEventListener('keydown', e => { if (e.key === 'Enter') loadTransactions(); });
  });

  document.querySelectorAll('#tx-table thead th[data-col]').forEach(th => {
    th.addEventListener('click', () => toggleSort(th.dataset.col));
  });

  loadTransactions();
});

function populatePropertySelects() {
  const selects = document.querySelectorAll('.property-type-select');
  selects.forEach(sel => {
    PROPERTY_TYPES.forEach(t => {
      const opt = document.createElement('option');
      opt.value = t;
      opt.textContent = t;
      sel.appendChild(opt);
    });
  });
}

// ─── Data Loading ──────────────────────────────────────────────────────────────

async function loadTransactions() {
  const params = buildFilterParams();
  const res = await apiFetch(`${API}/transactions?${params}`);
  if (!res) return;
  transactions = res;
  renderTable();
  updateCount();
}

function buildFilterParams() {
  const p = new URLSearchParams();
  const v = id => document.getElementById(id).value.trim();
  if (v('f-municipality')) p.set('municipality', v('f-municipality'));
  if (v('f-type')) p.set('property_type', v('f-type'));
  if (v('f-buyer')) p.set('buyer', v('f-buyer'));
  if (v('f-seller')) p.set('seller', v('f-seller'));
  if (v('f-date-from')) p.set('date_from', v('f-date-from'));
  if (v('f-date-to')) p.set('date_to', v('f-date-to'));
  if (v('f-price-min')) p.set('price_min', v('f-price-min'));
  if (v('f-price-max')) p.set('price_max', v('f-price-max'));
  return p;
}

function clearFilters() {
  document.querySelectorAll('#filter-panel input, #filter-panel select').forEach(el => {
    el.value = '';
  });
  loadTransactions();
}

// ─── Table Rendering ──────────────────────────────────────────────────────────

function renderTable() {
  const tbody = document.getElementById('table-body');
  const empty = document.getElementById('empty-state');

  if (!transactions.length) {
    tbody.innerHTML = '';
    empty.style.display = '';
    return;
  }
  empty.style.display = 'none';

  tbody.innerHTML = transactions.map(t => `
    <tr data-id="${t.id}" onclick="openDetail(${t.id})">
      <td class="text-muted" style="white-space:nowrap">${fmtDate(t.transaction_date)}</td>
      <td class="td-buyer-seller">
        <span class="td-buyer">${esc(t.buyer)}</span>
        <span class="td-seller">← ${esc(t.seller)}</span>
      </td>
      <td class="price-cell">${fmtPrice(t.price_sek, t.price_text)}</td>
      <td><span class="badge-type ${TYPE_BADGE_CLASS[t.property_type] || 'badge-ovrigt'}">${esc(t.property_type)}</span></td>
      <td class="td-location">
        <span class="td-muni">${esc(t.municipality || '–')}</span>
        <span class="td-address">${esc(t.address || '')}</span>
      </td>
      <td class="td-detail">${fmtArea(t.area_sqm, t.residential_units)}</td>
      <td class="td-detail">${t.yield_percent ? t.yield_percent.toFixed(2) + '%' : '–'}</td>
      <td>${t.source_url ? `<a href="${esc(t.source_url)}" target="_blank" class="source-link" onclick="event.stopPropagation()" title="${esc(t.source_name || 'Källa')}"><i class="bi bi-box-arrow-up-right"></i></a>` : '–'}</td>
      <td>
        <span title="${t.summary ? 'AI-analys klar' : 'Ingen AI-analys'}">${t.summary ? '<span class="ai-dot"></span>' : '<span class="no-ai-dot"></span>'}</span>
      </td>
      <td onclick="event.stopPropagation()">
        <button class="action-btn" title="Redigera" onclick="openEditForm(${t.id})"><i class="bi bi-pencil"></i></button>
        <button class="action-btn danger" title="Radera" onclick="confirmDelete(${t.id})"><i class="bi bi-trash"></i></button>
      </td>
    </tr>
  `).join('');
}

function updateCount() {
  const el = document.getElementById('result-count');
  el.innerHTML = `<strong>${transactions.length}</strong> affär${transactions.length !== 1 ? 'er' : ''} visas`;
}

// ─── Sorting ──────────────────────────────────────────────────────────────────

function toggleSort(col) {
  if (sortCol === col) {
    sortDir = sortDir === 'asc' ? 'desc' : 'asc';
  } else {
    sortCol = col;
    sortDir = 'desc';
  }

  document.querySelectorAll('#tx-table thead th[data-col]').forEach(th => {
    th.classList.remove('sort-asc', 'sort-desc');
    if (th.dataset.col === sortCol) {
      th.classList.add(sortDir === 'asc' ? 'sort-asc' : 'sort-desc');
    }
  });

  transactions.sort((a, b) => {
    let va = a[sortCol], vb = b[sortCol];
    if (va == null) return 1;
    if (vb == null) return -1;
    if (typeof va === 'string') va = va.toLowerCase();
    if (typeof vb === 'string') vb = vb.toLowerCase();
    return (va < vb ? -1 : va > vb ? 1 : 0) * (sortDir === 'asc' ? 1 : -1);
  });
  renderTable();
}

// ─── Add / Edit Form ──────────────────────────────────────────────────────────

function openAddForm() {
  currentEditId = null;
  document.getElementById('txModalLabel').textContent = 'Ny fastighetsaffär';
  document.getElementById('form-tx').reset();
  txModal.show();
}

async function openEditForm(id) {
  currentEditId = id;
  const tx = await apiFetch(`${API}/transactions/${id}`);
  if (!tx) return;
  document.getElementById('txModalLabel').textContent = 'Redigera affär';
  fillForm(tx);
  txModal.show();
}

function fillForm(t) {
  const set = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.value = val ?? '';
  };
  set('f-buyer', t.buyer);
  set('f-seller', t.seller);
  set('f-price-sek', t.price_sek);
  set('f-price-text', t.price_text);
  set('f-prop-type', t.property_type);
  set('f-designation', t.property_designation);
  set('f-address', t.address);
  set('f-municipality', t.municipality);
  set('f-county', t.county);
  set('f-tx-date', t.transaction_date);
  set('f-access-date', t.access_date);
  set('f-source-name', t.source_name);
  set('f-source-url', t.source_url);
  set('f-area', t.area_sqm);
  set('f-units', t.residential_units);
  set('f-tenants', t.tenants);
  set('f-yield', t.yield_percent);
  set('f-confidence', t.confidence_score);
  set('f-raw', t.raw_text);
  document.getElementById('f-portfolio').checked = !!t.portfolio_flag;
}

async function saveTx(e) {
  e.preventDefault();
  const data = collectForm();
  const url = currentEditId ? `${API}/transactions/${currentEditId}` : `${API}/transactions`;
  const method = currentEditId ? 'PUT' : 'POST';
  const res = await apiFetch(url, { method, body: JSON.stringify(data) });
  if (!res) return;
  txModal.hide();
  toast('Affären sparades', 'success');
  loadTransactions();
}

function collectForm() {
  const num = id => { const v = document.getElementById(id).value; return v === '' ? null : parseFloat(v); };
  const str = id => document.getElementById(id).value.trim() || null;
  const dte = id => document.getElementById(id).value || null;
  return {
    buyer: document.getElementById('f-buyer').value.trim(),
    seller: document.getElementById('f-seller').value.trim(),
    price_sek: num('f-price-sek'),
    price_text: str('f-price-text'),
    property_type: document.getElementById('f-prop-type').value,
    property_designation: str('f-designation'),
    address: str('f-address'),
    municipality: str('f-municipality'),
    county: str('f-county'),
    transaction_date: dte('f-tx-date'),
    access_date: dte('f-access-date'),
    source_name: str('f-source-name'),
    source_url: str('f-source-url'),
    area_sqm: num('f-area'),
    residential_units: num('f-units') !== null ? Math.round(num('f-units')) : null,
    tenants: str('f-tenants'),
    yield_percent: num('f-yield'),
    portfolio_flag: document.getElementById('f-portfolio').checked,
    confidence_score: num('f-confidence'),
    raw_text: str('f-raw'),
    summary: null,
    market_comment: null,
  };
}

// ─── Detail View ──────────────────────────────────────────────────────────────

async function openDetail(id) {
  currentDetailId = id;
  const tx = transactions.find(t => t.id === id) || await apiFetch(`${API}/transactions/${id}`);
  if (!tx) return;
  renderDetail(tx);
  detailModal.show();
}

function renderDetail(t) {
  document.getElementById('detailModalLabel').textContent = `${esc(t.buyer)} ← ${esc(t.seller)}`;

  const field = (label, val) => `
    <div class="detail-item">
      <label>${label}</label>
      <span>${val || '–'}</span>
    </div>`;

  const fullField = (label, val) => `
    <div class="detail-item full">
      <label>${label}</label>
      <span>${val || '–'}</span>
    </div>`;

  document.getElementById('detail-basics').innerHTML = `
    <div class="detail-grid">
      ${field('Köpare', `<strong>${esc(t.buyer)}</strong>`)}
      ${field('Säljare', `<strong>${esc(t.seller)}</strong>`)}
      ${field('Pris', `<strong>${fmtPrice(t.price_sek, t.price_text)}</strong>`)}
      ${field('Pris (text)', esc(t.price_text))}
      ${field('Fastighetstyp', `<span class="badge-type ${TYPE_BADGE_CLASS[t.property_type] || 'badge-ovrigt'}">${esc(t.property_type)}</span>`)}
      ${field('Portfölj', t.portfolio_flag ? 'Ja' : 'Nej')}
      ${field('Affärsdatum', fmtDate(t.transaction_date))}
      ${field('Tillträdesdatum', fmtDate(t.access_date))}
    </div>`;

  document.getElementById('detail-location').innerHTML = `
    <div class="detail-grid">
      ${field('Fastighetsbeteckning', esc(t.property_designation))}
      ${field('Adress', esc(t.address))}
      ${field('Kommun', esc(t.municipality))}
      ${field('Län', esc(t.county))}
    </div>`;

  document.getElementById('detail-details').innerHTML = `
    <div class="detail-grid">
      ${field('Area (kvm)', t.area_sqm ? t.area_sqm.toLocaleString('sv-SE') + ' kvm' : null)}
      ${field('Antal lägenheter', t.residential_units)}
      ${field('Direktavkastning', t.yield_percent ? t.yield_percent.toFixed(2) + '%' : null)}
      ${field('Tillförlitlighet', t.confidence_score ? (t.confidence_score * 100).toFixed(0) + '%' : null)}
      ${fullField('Hyresgäster', esc(t.tenants))}
      ${field('Källnamn', t.source_url ? `<a href="${esc(t.source_url)}" target="_blank">${esc(t.source_name || t.source_url)}</a>` : esc(t.source_name))}
      ${fullField('Råtext', esc(t.raw_text))}
    </div>`;

  renderAISection(t);
}

function renderAISection(t) {
  const summaryEl = document.getElementById('detail-summary');
  const commentEl = document.getElementById('detail-market');
  summaryEl.innerHTML = t.summary
    ? `<p class="ai-text">${esc(t.summary)}</p>`
    : `<p class="ai-placeholder">Ingen sammanfattning ännu. Klicka "Generera AI-analys" nedan.</p>`;
  commentEl.innerHTML = t.market_comment
    ? `<p class="ai-text">${esc(t.market_comment)}</p>`
    : `<p class="ai-placeholder">Ingen marknadskommentar ännu.</p>`;
}

function editFromDetail() {
  detailModal.hide();
  openEditForm(currentDetailId);
}

async function deleteFromDetail() {
  if (!confirm('Radera denna affär? Åtgärden kan inte ångras.')) return;
  const ok = await apiFetch(`${API}/transactions/${currentDetailId}`, { method: 'DELETE' }, true);
  if (ok !== null) {
    detailModal.hide();
    toast('Affären raderades', 'warning');
    loadTransactions();
  }
}

// ─── Delete ───────────────────────────────────────────────────────────────────

async function confirmDelete(id) {
  if (!confirm('Radera denna affär?')) return;
  const ok = await apiFetch(`${API}/transactions/${id}`, { method: 'DELETE' }, true);
  if (ok !== null) {
    toast('Affären raderades', 'warning');
    loadTransactions();
  }
}

// ─── AI Summary ───────────────────────────────────────────────────────────────

async function generateSummary() {
  const btn = document.getElementById('btn-summarize');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Genererar...';

  const res = await apiFetch(`${API}/transactions/${currentDetailId}/summarize`, { method: 'POST' });
  btn.disabled = false;
  btn.innerHTML = '<i class="bi bi-stars me-1"></i>Generera AI-analys';

  if (!res) return;

  const idx = transactions.findIndex(t => t.id === currentDetailId);
  if (idx >= 0) {
    transactions[idx].summary = res.summary;
    transactions[idx].market_comment = res.market_comment;
  }
  renderAISection({ summary: res.summary, market_comment: res.market_comment });
  toast('AI-analys genererades', 'success');
}

// ─── Export ───────────────────────────────────────────────────────────────────

function exportCSV() {
  const params = buildFilterParams();
  window.location = `${API}/export/csv?${params}`;
}

// ─── Import ───────────────────────────────────────────────────────────────────

function fillSample() {
  document.getElementById('import-json').value = JSON.stringify(SAMPLE_JSON, null, 2);
}

async function doImport() {
  const raw = document.getElementById('import-json').value.trim();
  let data;
  try {
    data = JSON.parse(raw);
    if (!Array.isArray(data)) data = [data];
  } catch {
    toast('Ogiltig JSON — kontrollera formatet', 'danger');
    return;
  }
  const res = await apiFetch(`${API}/transactions/import`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
  if (!res) return;
  importModal.hide();
  document.getElementById('import-json').value = '';
  toast(`${res.length} affär${res.length !== 1 ? 'er' : ''} importerades`, 'success');
  loadTransactions();
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmtDate(d) {
  if (!d) return '–';
  return d.substring(0, 10);
}

function fmtPrice(sek, text) {
  if (text) return text;
  if (!sek) return '–';
  if (sek >= 1e9) return `${(sek / 1e9).toFixed(2).replace('.', ',')} mdSEK`.replace(',00', '');
  if (sek >= 1e6) return `${Math.round(sek / 1e6)} MSEK`;
  return `${sek.toLocaleString('sv-SE')} SEK`;
}

function fmtArea(sqm, units) {
  const parts = [];
  if (sqm) parts.push(`${sqm.toLocaleString('sv-SE')} kvm`);
  if (units) parts.push(`${units} lgh`);
  return parts.join(' / ') || '–';
}

function esc(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

async function apiFetch(url, opts = {}, noContent = false) {
  try {
    const res = await fetch(url, {
      headers: { 'Content-Type': 'application/json' },
      ...opts,
    });
    if (noContent && res.status === 204) return {};
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      toast(err.detail || 'Serverfel', 'danger');
      return null;
    }
    if (res.status === 204) return {};
    return await res.json();
  } catch (e) {
    toast(`Nätverksfel: ${e.message}`, 'danger');
    return null;
  }
}

function toast(msg, type = 'success') {
  const el = document.createElement('div');
  el.className = `toast align-items-center text-white bg-${type === 'warning' ? 'warning text-dark' : type} border-0`;
  el.setAttribute('role', 'alert');
  el.setAttribute('aria-live', 'assertive');
  el.innerHTML = `
    <div class="d-flex">
      <div class="toast-body">${esc(msg)}</div>
      <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
    </div>`;
  document.getElementById('toast-container').appendChild(el);
  const t = new bootstrap.Toast(el, { delay: 3500 });
  t.show();
  el.addEventListener('hidden.bs.toast', () => el.remove());
}
