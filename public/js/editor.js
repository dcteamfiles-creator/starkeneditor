// SX Editor v4 — Auto-Gen, Click-Picker, Slider, Progress, PDF-Support

const SECTIONS = [
  { key: 'positionierung',     de: 'Positionierung',                     en: 'Authentic Value Proposition',  max: 400 },
  { key: 'alleinstellung',     de: 'Alleinstellung',                     en: 'Unfair Advantage',             max: 320 },
  { key: 'fuehrungsstil',      de: 'Führungsstil',                       en: 'Leadership-Impact-Matrix',     max: 280 },
  { key: 'einsatzgebiete',     de: 'Einsatzgebiete',                     en: 'Areas of Personal excellence & flow', max: 320 },
  { key: 'belastbarkeit',      de: 'Belastbarkeit',                      en: 'Resilience-Profile',           max: 280 },
  { key: 'zukunftskompetenz',  de: 'Zukunftskompetenz (KI-Resilienz)',   en: 'Future Skills',                max: 360 },
  { key: 'unternehmenskultur', de: 'Unternehmenskultur',                 en: 'Culture-Fit Analysis',         max: 280 },
];

const sectionStrengths = {};
SECTIONS.forEach(s => sectionStrengths[s.key] = []);
let availableStrengths = [];
let dimensions = {AE: [], ED: [], SH: [], WK: []};
let defaultPromptCache = '';

// ─── PROGRESS BAR ────────────────────────────────────────────────
function showProgress(label, indeterminate=true) {
  const ct = document.getElementById('progress-container');
  const fill = document.getElementById('progress-fill');
  const lbl = document.getElementById('progress-label');
  ct.style.display = 'block';
  lbl.textContent = label;
  fill.classList.toggle('indeterminate', indeterminate);
  if (indeterminate) fill.style.width = '30%';
}
function setProgress(percent, label) {
  const fill = document.getElementById('progress-fill');
  const lbl = document.getElementById('progress-label');
  fill.classList.remove('indeterminate');
  fill.style.width = percent + '%';
  if (label) lbl.textContent = label;
}
function hideProgress() {
  document.getElementById('progress-container').style.display = 'none';
}

// ─── BUILD SECTION INPUTS ────────────────────────────────────────
const secCt = document.getElementById('sections-container');
SECTIONS.forEach(s => {
  const block = document.createElement('div');
  block.className = 'section-block';
  block.dataset.key = s.key;
  block.innerHTML = `
    <div class="section-head">
      <span class="titles">${s.de}<span class="en">// ${s.en}</span></span>
      <span class="counter" data-for="${s.key}">0 / ${s.max}</span>
    </div>
    <div class="strength-tags" data-strengths-for="${s.key}">
      <span class="strength-tag placeholder">Lade Auswertung hoch — Stärken erscheinen hier.</span>
    </div>
    <textarea id="sec-${s.key}" maxlength="${s.max}" placeholder="KI generiert Text — du editierst (max. ${s.max} Zeichen)"></textarea>
    <div style="display:flex;gap:6px;margin-top:6px">
      <button type="button" class="secondary" data-regen="${s.key}" style="font-size:0.78rem;padding:4px 10px">⟳ Diesen Text neu generieren</button>
    </div>
  `;
  secCt.appendChild(block);
  const ta = block.querySelector('textarea');
  const counter = block.querySelector('.counter');
  ta.addEventListener('input', () => {
    counter.textContent = `${ta.value.length} / ${s.max}`;
    counter.classList.toggle('warn', ta.value.length > s.max * 0.85);
    counter.classList.toggle('over', ta.value.length >= s.max);
    refreshPreview();
  });
});

secCt.addEventListener('click', async (ev) => {
  const btn = ev.target.closest('[data-regen]');
  if (!btn) return;
  const key = btn.dataset.regen;
  await generateAllTexts([key]);
});

// ─── UPLOADS HELPERS ─────────────────────────────────────────────
async function uploadFile(file, kind) {
  const fd = new FormData();
  fd.append('file', file); fd.append('kind', kind);
  const r = await fetch('/api/upload', {method: 'POST', body: fd});
  if (!r.ok) { alert('Upload fehlgeschlagen'); return ''; }
  const j = await r.json();
  return j.url;
}

// ─── AUSWERTUNG-UPLOAD via Vision ───────────────────────────────
const dropZone = document.getElementById('upload-zone');
const dropFile = document.getElementById('upload-file');
const dropStatus = document.getElementById('upload-status');

dropZone.onclick = () => dropFile.click();
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop', e => {
  e.preventDefault(); dropZone.classList.remove('dragover');
  if (e.dataTransfer.files[0]) handleAuswertungUpload(e.dataTransfer.files[0]);
});
dropFile.onchange = e => { if (e.target.files[0]) handleAuswertungUpload(e.target.files[0]); };

async function handleAuswertungUpload(file) {
  dropZone.classList.add('has-file');
  dropZone.querySelector('.dz-title').textContent = `📎 ${file.name}`;
  dropZone.querySelector('.dz-icon').textContent = '⏳';
  dropStatus.innerHTML = '';
  showProgress('Schritt 1/3: Stärken aus Auswertung extrahieren (~10-20 Sek)…');

  try {
    const fd = new FormData();
    fd.append('file', file); fd.append('kind', 'auswertung');
    const r = await fetch('/api/import-from-screenshot', {method: 'POST', body: fd});
    if (!r.ok) {
      const err = await r.json().catch(() => ({error: 'unknown'}));
      throw new Error(err.error);
    }
    const j = await r.json();
    document.getElementById('vorname').value = j.vorname || '';
    document.getElementById('nachname').value = j.nachname || '';
    dimensions = j.dimensions || {AE: [], ED: [], SH: [], WK: []};
    availableStrengths = [...new Set([...dimensions.AE, ...dimensions.ED, ...dimensions.SH, ...dimensions.WK])];
    const sd = j.section_strengths_default || {};
    Object.keys(sectionStrengths).forEach(k => sectionStrengths[k] = sd[k] || []);
    renderAllStrengthTags();
    dropZone.querySelector('.dz-icon').textContent = '✓';
    dropStatus.innerHTML = `<span class="status-pill success">✓ ${availableStrengths.length} Stärken erkannt · ${j.vorname} ${j.nachname}</span>`;
    refreshPreview();

    // Auto-Generate: 7 Texte + 3 Header in Series
    showProgress('Schritt 2/3: 7 Texte generieren (~10-15 Sek)…');
    await generateAllTexts(null, false);
    showProgress('Schritt 3/3: 3 Header-Vorschläge generieren (~3-5 Sek)…');
    await generateHeaders(false);
    setProgress(100, '✓ Fertig! Alles bereit zum Editieren.');
    setTimeout(hideProgress, 2000);
  } catch (e) {
    hideProgress();
    dropZone.querySelector('.dz-icon').textContent = '⚠';
    dropStatus.innerHTML = `<span class="status-pill" style="background:#fceced;color:#c13">⚠ ${e.message}</span>`;
  }
}

// ─── STRENGTH TAGS PER SEKTION ──────────────────────────────────
function renderAllStrengthTags() {
  SECTIONS.forEach(s => renderTagsForSection(s.key));
}
function renderTagsForSection(key) {
  const container = document.querySelector(`.strength-tags[data-strengths-for="${key}"]`);
  if (!container) return;
  const selected = sectionStrengths[key];
  if (!selected.length && !availableStrengths.length) {
    container.innerHTML = '<span class="strength-tag placeholder">Lade Auswertung hoch — Stärken erscheinen hier.</span>';
    return;
  }
  container.innerHTML = '';
  for (const st of selected) {
    const tag = document.createElement('span');
    tag.className = 'strength-tag';
    tag.innerHTML = `${st} <span class="remove">×</span>`;
    tag.title = 'Klick zum Entfernen';
    tag.onclick = () => {
      sectionStrengths[key] = sectionStrengths[key].filter(x => x !== st);
      renderTagsForSection(key);
    };
    container.appendChild(tag);
  }
  const add = document.createElement('button');
  add.type = 'button'; add.className = 'add-strength-btn';
  add.textContent = '+ Stärke';
  add.onclick = () => openStrengthPicker(key);
  container.appendChild(add);
}

// ─── STRENGTH PICKER MODAL ──────────────────────────────────────
const pickerModal = document.getElementById('picker-modal');
const pickerTags = document.getElementById('picker-tags');
const pickerSectionName = document.getElementById('picker-section-name');
let activePickerSection = null;

function openStrengthPicker(key) {
  activePickerSection = key;
  const sec = SECTIONS.find(s => s.key === key);
  pickerSectionName.textContent = `→ ${sec.de}`;
  renderPickerTags();
  pickerModal.style.display = 'flex';
}
function renderPickerTags() {
  pickerTags.innerHTML = '';
  if (!availableStrengths.length) {
    pickerTags.innerHTML = '<p class="muted" style="text-align:center;padding:20px;">Noch keine Stärken erkannt — erst Auswertung hochladen.</p>';
    return;
  }
  // Group by Dimension
  const dimGroups = [
    {label: 'WK · Wissen und Können', items: dimensions.WK || []},
    {label: 'AE · Auftreten und Erscheinung', items: dimensions.AE || []},
    {label: 'SH · Sprechen und Handeln', items: dimensions.SH || []},
    {label: 'ED · Einstellung und Denken', items: dimensions.ED || []},
  ];
  for (const g of dimGroups) {
    if (!g.items.length) continue;
    const heading = document.createElement('div');
    heading.style.cssText = 'width:100%; font-size:0.7rem; font-weight:700; letter-spacing:0.06em; text-transform:uppercase; color:var(--brand-blue-dk); margin: 8px 0 4px;';
    heading.textContent = g.label;
    pickerTags.appendChild(heading);
    for (const st of g.items) {
      const isSelected = sectionStrengths[activePickerSection].includes(st);
      const tag = document.createElement('span');
      tag.className = 'strength-tag' + (isSelected ? ' disabled' : '');
      tag.textContent = st + (isSelected ? ' ✓' : '');
      tag.onclick = () => {
        if (!isSelected) {
          sectionStrengths[activePickerSection].push(st);
          renderPickerTags();
        }
      };
      pickerTags.appendChild(tag);
    }
  }
}
document.getElementById('picker-close').onclick = () => closePickerModal();
document.getElementById('picker-done').onclick = () => closePickerModal();
pickerModal.addEventListener('click', e => { if (e.target === pickerModal) closePickerModal(); });
function closePickerModal() {
  pickerModal.style.display = 'none';
  if (activePickerSection) renderTagsForSection(activePickerSection);
  activePickerSection = null;
}

// ─── KI: Texte generieren ───────────────────────────────────────
async function generateAllTexts(onlyKeys = null, withProgress = true) {
  if (!availableStrengths.length) { alert('Erst Auswertung hochladen.'); return; }
  const btn = document.getElementById('generate-all-texts');
  if (!onlyKeys && btn) { btn.disabled = true; btn.textContent = '⏳ Generiere 7 Texte… (~15 Sek)'; }
  if (onlyKeys) onlyKeys.forEach(k => {
    const block = secCt.querySelector(`[data-key="${k}"]`);
    if (block) block.classList.add('generating');
  });
  if (withProgress) showProgress('Generiere 7 Texte mit Claude…');
  try {
    const r = await fetch('/api/generate-texts', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        section_strengths: sectionStrengths,
        vorname: document.getElementById('vorname').value,
        nachname: document.getElementById('nachname').value,
        system_prompt: document.getElementById('system_prompt').value || null,
      }),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({error:'unknown'}));
      throw new Error(err.error);
    }
    const j = await r.json();
    Object.entries(j.sections).forEach(([k, txt]) => {
      if (onlyKeys && !onlyKeys.includes(k)) return;
      const ta = document.getElementById(`sec-${k}`);
      if (ta) {
        ta.value = txt;
        ta.dispatchEvent(new Event('input'));
      }
    });
  } catch (e) {
    alert('KI-Fehler: ' + e.message);
  } finally {
    if (!onlyKeys && btn) { btn.disabled = false; btn.textContent = '⚡ Alle 7 Texte generieren'; }
    if (onlyKeys) onlyKeys.forEach(k => {
      const block = secCt.querySelector(`[data-key="${k}"]`);
      if (block) block.classList.remove('generating');
    });
    if (withProgress) hideProgress();
  }
  refreshPreview();
}

document.getElementById('generate-all-texts').onclick = () => generateAllTexts();

// ─── KI: Header ─────────────────────────────────────────────────
async function generateHeaders(withProgress = true) {
  if (!availableStrengths.length) { alert('Erst Auswertung hochladen.'); return; }
  const btn = document.getElementById('generate-headers');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Generiere…'; }
  if (withProgress) showProgress('Generiere 3 Header-Varianten…');
  try {
    const r = await fetch('/api/generate-headers', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        section_strengths: sectionStrengths,
        vorname: document.getElementById('vorname').value,
      }),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({error:'unknown'}));
      throw new Error(err.error);
    }
    const j = await r.json();
    renderHeaderAlts(j.alternatives || []);
  } catch (e) {
    alert('Header-Fehler: ' + e.message);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '⚡ 3 Header-Varianten generieren'; }
    if (withProgress) hideProgress();
  }
}

function renderHeaderAlts(alts) {
  const ct = document.getElementById('header-alts');
  ct.innerHTML = '';
  if (!alts.length) {
    ct.innerHTML = '<div class="header-alt placeholder muted" style="text-align:center;font-style:italic">Keine Vorschläge erhalten.</div>';
    return;
  }
  alts.forEach(a => {
    const div = document.createElement('div');
    div.className = 'header-alt';
    div.innerHTML = `<div class="alt-style">${a.style}</div><div class="alt-text">${a.text}</div>`;
    div.onclick = () => {
      ct.querySelectorAll('.header-alt').forEach(x => x.classList.remove('selected'));
      div.classList.add('selected');
      document.getElementById('header').value = a.text;
      document.getElementById('header').dispatchEvent(new Event('input'));
    };
    ct.appendChild(div);
  });
}

document.getElementById('generate-headers').onclick = () => generateHeaders();

// ─── PRN CLAIM ──────────────────────────────────────────────────
document.getElementById('claim-prn').onclick = async () => {
  const r = await fetch('/api/claim-prn', {method:'POST'});
  if (!r.ok) { alert('Keine freie Prüfnummer verfügbar'); return; }
  const j = await r.json();
  document.getElementById('pruefnummer').value = j.prn;
  refreshPreview();
};

// ─── SYSTEM-PROMPT EDITOR ───────────────────────────────────────
async function loadDefaultPrompt() {
  const r = await fetch('/api/default-prompt');
  if (!r.ok) return;
  const j = await r.json();
  defaultPromptCache = j.prompt || '';
  const ta = document.getElementById('system_prompt');
  if (!ta.value) ta.value = defaultPromptCache;
}
document.getElementById('reset-prompt').onclick = () => {
  if (confirm('Prompt auf Default zurücksetzen?')) {
    document.getElementById('system_prompt').value = defaultPromptCache;
  }
};

// ─── PREVIEW SIZE SLIDER ───────────────────────────────────────
const slider = document.getElementById('preview-size');
const grid = document.getElementById('editor-grid');
function applyPreviewSize() {
  const v = parseInt(slider.value);
  grid.classList.remove('preview-collapsed', 'preview-narrow', 'preview-wide');
  if (v <= 5) grid.classList.add('preview-collapsed');
  else if (v < 35) grid.classList.add('preview-narrow');
  else if (v > 65) grid.classList.add('preview-wide');
  // 35-65 = default 50/50 grid
  localStorage.setItem('sx-preview-size', v);
}
slider.addEventListener('input', applyPreviewSize);
const savedSize = localStorage.getItem('sx-preview-size');
if (savedSize !== null) slider.value = savedSize;

// ─── PAYLOAD ────────────────────────────────────────────────────
function getPayload() {
  const sections = {};
  SECTIONS.forEach(s => sections[s.key] = document.getElementById(`sec-${s.key}`).value || '');
  const vorname = document.getElementById('vorname').value;
  const nachname = document.getElementById('nachname').value;
  return {
    vorname, nachname,
    person_name: [vorname, nachname].filter(Boolean).join(' '),
    email: document.getElementById('email').value,
    header: document.getElementById('header').value,
    pruefnummer: document.getElementById('pruefnummer').value,
    feedback_count: parseInt(document.getElementById('feedback_count').value) || 3,
    date: document.getElementById('date').value || null,
    system_prompt: document.getElementById('system_prompt').value || null,
    section_strengths: sectionStrengths,
    dimensions: dimensions,
    sections,
  };
}

// ─── HTML LIVE-PREVIEW ──────────────────────────────────────────
const previewEl = document.getElementById('html-preview');
function refreshPreview() {
  const p = getPayload();
  const sections = SECTIONS.map(s => `
    <div class="prev-section">
      <div class="prev-head"><strong>${s.de}</strong> <span class="sep">//</span> <span class="en">${s.en}</span></div>
      <div class="prev-body">${(p.sections[s.key] || '<em class="muted">(noch leer)</em>').replace(/\n/g, '<br>')}</div>
    </div>`).join('');
  previewEl.innerHTML = `
    <div class="prev-header-bar">
      <div class="prev-name-block">
        <div class="prev-id">ID-Type-Person:</div>
        <div class="prev-name">${p.person_name || '<em class="muted">(Vorname Nachname)</em>'}</div>
        <div class="prev-subtitle">Basierend auf Multi-Source-Feedback<br>gemäß Qualitätsstandards des Stärkenkompass-Audits</div>
      </div>
      <div class="prev-title-pill">Stärken-Exposé</div>
    </div>
    <div class="prev-meta">
      <div><strong>Email:</strong> ${p.email || '—'}</div>
      <div><strong>Prüfnummer:</strong> ${p.pruefnummer ? '#'+p.pruefnummer.replace(/^#/,'') : '<em class="muted">(noch leer)</em>'}</div>
      <div><strong>Feedbacks:</strong> ${p.feedback_count || 3}</div>
      <div><strong>Datum:</strong> ${p.date || '(heute)'}</div>
    </div>
    <div class="prev-header">${p.header || '<em class="muted">(Affirmation Header — Schritt 5)</em>'}</div>
    <div class="prev-sections">${sections}</div>
    <p class="muted" style="margin-top:14px;font-size:0.78rem;text-align:center;">
      Sponsor &amp; Schirmherren werden in Canva manuell ergänzt.
    </p>
  `;
}

['vorname', 'nachname', 'email', 'header', 'pruefnummer', 'feedback_count', 'date']
  .forEach(id => document.getElementById(id).addEventListener('input', refreshPreview));

// ─── FREIGEBEN ─────────────────────────────────────────────────
document.getElementById('add-to-queue').onclick = async () => {
  const payload = getPayload();
  const errors = [];
  if (!payload.vorname || !payload.nachname) errors.push('Vorname & Nachname fehlen');
  if (!payload.email) errors.push('Email fehlt');
  if (!payload.pruefnummer) errors.push('Prüfnummer fehlt — bitte freie PRN holen');
  if (!payload.header) errors.push('Affirmation-Header fehlt');
  const emptySections = SECTIONS.filter(s => !payload.sections[s.key]?.trim()).map(s => s.de);
  if (emptySections.length) errors.push(`Leere Sektionen: ${emptySections.join(', ')}`);
  if (errors.length) {
    alert('Bitte beheben:\n\n• ' + errors.join('\n• '));
    return;
  }
  const r = await fetch('/api/bulk-queue', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
  if (!r.ok) { alert('Fehler beim Speichern in Queue'); return; }
  const entry = await r.json();
  alert(`✓ SX für "${payload.person_name}" in Bulk-Queue gelegt.\nID: ${entry.id}`);
  await updateQueueCount();
  if (confirm('Formular für nächstes SX leeren?')) resetForm();
};

document.getElementById('reset-form').onclick = () => { if (confirm('Formular leeren? (Prompt + Größen-Einstellung bleiben)')) resetForm(); };

function resetForm() {
  document.querySelectorAll('input, textarea').forEach(el => {
    if (el.type === 'hidden') return;
    if (el.id === 'feedback_count') return;
    if (el.id === 'system_prompt') return;
    el.value = '';
  });
  document.getElementById('feedback_count').value = '3';
  Object.keys(sectionStrengths).forEach(k => sectionStrengths[k] = []);
  availableStrengths = []; dimensions = {AE: [], ED: [], SH: [], WK: []};
  renderAllStrengthTags();
  document.querySelectorAll('.counter').forEach(c => { c.textContent = '0 / —'; c.classList.remove('warn', 'over'); });
  dropZone.classList.remove('has-file');
  dropZone.querySelector('.dz-title').textContent = 'PDF oder Screenshot hier ablegen';
  dropZone.querySelector('.dz-icon').textContent = '📊';
  dropStatus.innerHTML = '';
  hideProgress();
  document.getElementById('header-alts').innerHTML = '<div class="header-alt placeholder muted" style="text-align:center;font-style:italic">Erst Auswertung hochladen — Vorschläge erscheinen hier.</div>';
  refreshPreview();
}

document.getElementById('logout').onclick = async () => {
  await fetch('/api/logout', {method:'POST'});
  location.href = '/';
};

async function updateQueueCount() {
  try {
    const r = await fetch('/api/bulk-queue');
    const list = await r.json();
    const pending = list.filter(e => e.status !== 'exported').length;
    document.getElementById('queue-count').textContent = pending > 0 ? pending : '';
  } catch {}
}

// ─── INIT ───────────────────────────────────────────────────────
(async () => {
  applyPreviewSize();
  await loadDefaultPrompt();
  await updateQueueCount();
  refreshPreview();
})();
