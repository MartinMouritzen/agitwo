// Shared voice-picker modal used by BOTH the character lab (lab.html) and the combat-barks page
// (barks.html) — one component, one behaviour. Filters: search + gender + age + language.
// Magnific voices first, then a separator, then the account's (metered) ElevenLabs voices.
//
// Host calls VoicePicker.open(config). Row buttons dispatch to internal handlers by index, so no
// host data is ever embedded in onclick strings (apostrophe-safe by construction).
//
// config:
//   voices        array of {voice_id,name,gender,age,accent,desc,preview,source,lang}
//   header        optional HTML shown above the filters (character/line context card)
//   gender/age    initial filter values ('' = any)
//   lang          initial language filter (default 'English'); applies to Magnific only, EL always shown
//   taken         {voice_id: 'OtherName'}  voices cast elsewhere (greyed + marker)
//   currentPickId highlight the currently-picked voice
//   primaryLabel  string OR (voice)=>string  label for the main action button
//   onPick        (voice, takenByName) => void   REQUIRED
//   onPreviewLine (voice) => void   optional; adds a "▶ first line" button per row
//   onRefresh     () => void        optional; adds a "↻ refresh catalog" button
//   onClear       () => void        optional; adds a clear button in the header bar
//   clearLabel    label for the clear button
//   keepOpenOnPick default false (close after a pick)
const VoicePicker = (function () {
  let cfg = null, rows = [], prevAudio = null;

  (function injectStyles() {
    const css = `
    #vpmodal{position:fixed;inset:0;background:rgba(0,0,0,.62);display:none;align-items:center;justify-content:center;z-index:80}
    #vpmodal.open{display:flex}
    #vpbox{width:min(920px,94vw);height:min(820px,94vh);background:var(--panel);border:1px solid var(--edge,var(--line,#2a2a38));
      border-radius:14px;display:flex;flex-direction:column;overflow:hidden}
    #vphead{display:flex;gap:10px;padding:12px 16px;border-bottom:1px solid var(--edge,var(--line,#2a2a38));align-items:center;flex-wrap:wrap}
    #vphead input,#vphead select{font:inherit;background:var(--panel2);color:var(--txt);border:1px solid var(--edge,var(--line,#2a2a38));border-radius:8px;padding:6px 10px}
    #vphead button{font:inherit;background:var(--panel2);color:var(--txt);border:1px solid var(--edge,var(--line,#2a2a38));border-radius:8px;padding:6px 11px;cursor:pointer}
    #vphead button:hover{background:#26303b}
    #vpctx{padding:12px 16px 2px}
    #vpctx .vcname{font-weight:700;font-size:15px}
    #vpctx .vcbio{font-size:12.5px;color:var(--dim)}
    #vpctx .ph{display:flex;align-items:center;justify-content:center;background:#232a33;border-radius:8px;font-weight:700;color:#55606c;font-size:20px}
    #vplist{flex:1;overflow-y:auto;padding:6px 12px 12px}
    .vp-row{display:flex;gap:12px;align-items:center;padding:9px 10px;border-bottom:1px solid rgba(255,255,255,.05)}
    .vp-row:hover{background:rgba(255,255,255,.035)}
    .vp-row.taken{opacity:.5}
    .vp-row .vn{font-weight:600;font-size:14px}
    .vp-row .vd{font-size:12.5px;color:var(--dim);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:520px}
    .vp-row .act{margin-left:auto;display:flex;gap:8px;flex:none}
    .vp-tag{font-size:11px;color:var(--acc2,var(--acc));border:1px solid var(--edge,var(--line,#2a2a38));border-radius:10px;padding:1px 8px;margin-left:6px}
    .vp-sep{position:sticky;top:0;margin:10px 2px 4px;padding:6px 10px;font-size:11px;font-weight:700;letter-spacing:.05em;color:var(--bad);
      background:rgba(246,102,102,.13);border-radius:6px;text-align:center}
    .vp-btn{font:inherit;background:var(--panel2);color:var(--txt);border:1px solid var(--edge,var(--line,#2a2a38));border-radius:7px;padding:4px 10px;cursor:pointer;font-size:12.5px;flex:none}
    .vp-btn:hover{background:#26303b}
    `;
    const s = document.createElement('style'); s.textContent = css; document.head.appendChild(s);
    const wrap = document.createElement('div');
    wrap.id = 'vpmodal';
    wrap.innerHTML =
      `<div id="vpbox">
         <div id="vpctx"></div>
         <div id="vphead">
           <input id="vpq" placeholder="Search voices (name, accent, vibe…)" style="flex:1;min-width:180px">
           <select id="vpg"><option value="">any gender</option><option value="male">male</option><option value="female">female</option><option value="neutral">neutral</option></select>
           <select id="vpage"><option value="">any age</option><option value="young">young</option><option value="middle_aged">middle aged</option><option value="old">old</option></select>
           <select id="vplang" title="Accent / language — defaults to English"></select>
           <button id="vprefresh" style="display:none">↻ refresh catalog</button>
           <button id="vpclear" style="display:none"></button>
           <button id="vpclose">✕</button>
         </div>
         <div id="vplist"></div>
       </div>`;
    document.body.appendChild(wrap);
    const $ = id => document.getElementById(id);
    $('vpq').oninput = render;
    $('vpg').onchange = render;
    $('vpage').onchange = render;
    $('vplang').onchange = render;
    $('vpclose').onclick = close;
    $('vpclear').onclick = () => { if (cfg && cfg.onClear) cfg.onClear(); };
    $('vprefresh').onclick = () => { if (cfg && cfg.onRefresh) cfg.onRefresh(); };
    wrap.addEventListener('click', e => { if (e.target === wrap) close(); });
  })();

  const $ = id => document.getElementById(id);
  const esc = t => { const d = document.createElement('div'); d.textContent = t == null ? '' : t; return d.innerHTML; };
  const isMag = v => v.source === 'magnific';
  const ageOf = v => (v.age || '').toLowerCase().replace(/-/g, '_');
  const langOf = v => isMag(v) ? (v.lang || 'English') : 'my ElevenLabs';

  function populateLangs(voices, want) {
    const counts = {};
    for (const v of voices) { const l = langOf(v); counts[l] = (counts[l] || 0) + 1; }
    const order = Object.entries(counts).sort((a, b) => (b[0] === 'English') - (a[0] === 'English') || b[1] - a[1]);
    const sel = $('vplang');
    sel.innerHTML = '<option value="__any">any language</option>' +
      order.map(([l, n]) => `<option value="${esc(l)}"${(want ? l === want : l === 'English') ? ' selected' : ''}>${esc(l)} (${n})</option>`).join('');
  }

  function play(url) { if (prevAudio) prevAudio.pause(); prevAudio = new Audio(url); prevAudio.play().catch(() => {}); }

  function rowHtml(v, i) {
    const taken = cfg.taken && cfg.taken[v.voice_id];
    const isPick = v.voice_id === cfg.currentPickId;
    const mag = isMag(v);
    const srcTag = mag ? `<span class="vp-tag" style="color:var(--acc)">Magnific</span>`
      : (v.source === 'library' ? `<span class="vp-tag" style="color:var(--bad)">EL library · metered · adds on use</span>`
        : `<span class="vp-tag" style="color:var(--bad)">my ElevenLabs (metered)</span>`);
    const bg = isPick ? 'background:rgba(104,211,145,.16)' : (mag ? '' : 'background:rgba(246,102,102,.08)');
    const label = typeof cfg.primaryLabel === 'function' ? cfg.primaryLabel(v) : (cfg.primaryLabel || 'Use');
    const ageDisp = ageOf(v).replace(/_/g, ' ');
    return `<div class="vp-row ${taken ? 'taken' : ''}" style="${bg}">
      <div><div class="vn">${esc(v.name || '?')}${srcTag}
        ${v.gender ? `<span class="vp-tag">${esc(v.gender)}</span>` : ''}${ageDisp ? `<span class="vp-tag">${esc(ageDisp)}</span>` : ''}${v.accent ? `<span class="vp-tag">${esc(v.accent)}</span>` : ''}
        ${isPick ? '<span class="vp-tag" style="color:var(--good)">current pick</span>' : ''}
        ${taken ? `<span class="vp-tag" style="color:var(--bad)">cast as ${esc(taken)}</span>` : ''}</div>
        <div class="vd">${esc(v.desc || '')}</div></div>
      <div class="act">
        ${v.preview ? `<button class="vp-btn" onclick="VoicePicker._preview(${i})">▶ preview</button>` : ''}
        ${cfg.onPreviewLine ? `<button class="vp-btn" onclick="VoicePicker._previewLine(${i})" title="Generate this line with this voice and play it">▶ first line</button>` : ''}
        <button class="vp-btn" onclick="VoicePicker._pick(${i})"${taken ? ` title="Already cast as ${esc(taken)} — click to use anyway"` : ''}>${esc(label)}</button>
      </div></div>`;
  }

  function render() {
    if (!cfg) return;
    const q = ($('vpq').value || '').toLowerCase(), g = $('vpg').value, age = $('vpage').value, lang = $('vplang').value || 'English';
    const matchQ = v => !q || `${v.name} ${v.desc || ''} ${v.accent || ''} ${v.use || ''} ${v.age || ''}`.toLowerCase().includes(q);
    const matchG = v => !g || (v.gender || '') === g;
    const matchA = v => !age || ageOf(v) === age;
    const base = (cfg.voices || []).filter(v => matchQ(v) && matchG(v) && matchA(v));
    const mags = base.filter(v => isMag(v) && (lang === '__any' || langOf(v) === lang)).slice(0, 300);
    const els = base.filter(v => !isMag(v));
    rows = [...mags, ...els];
    const sep = els.length ? '<div class="vp-sep">↓ My ElevenLabs voices (metered quota) ↓</div>' : '';
    const magHtml = mags.map((v, i) => rowHtml(v, i)).join('');
    const elHtml = els.map((v, i) => rowHtml(v, mags.length + i)).join('');
    $('vplist').innerHTML = (magHtml + sep + elHtml) || '<div style="padding:22px;color:var(--dim)">No matches</div>';
  }

  function open(config) {
    cfg = config;
    $('vpctx').innerHTML = config.header || '';
    $('vpctx').style.display = config.header ? '' : 'none';
    $('vpq').value = '';
    $('vpg').value = config.gender || '';
    $('vpage').value = config.age || '';
    populateLangs(config.voices || [], config.lang);
    $('vprefresh').style.display = config.onRefresh ? '' : 'none';
    const clr = $('vpclear');
    if (config.onClear) { clr.style.display = ''; clr.textContent = config.clearLabel || '↺ clear'; }
    else clr.style.display = 'none';
    render();
    $('vpmodal').classList.add('open');
    $('vpq').focus();
  }
  function close() { $('vpmodal').classList.remove('open'); cfg = null; }

  return {
    open, close, refresh: render,
    setVoices(arr) { if (cfg) { cfg.voices = arr; populateLangs(arr, $('vplang').value); render(); } },
    _pick(i) { const v = rows[i]; if (!v || !cfg) return; const t = cfg.taken && cfg.taken[v.voice_id]; cfg.onPick(v, t); if (!cfg.keepOpenOnPick) close(); },
    _preview(i) { const v = rows[i]; if (v && v.preview) play(v.preview); },
    _previewLine(i) { const v = rows[i]; if (v && cfg && cfg.onPreviewLine) cfg.onPreviewLine(v); },
  };
})();
