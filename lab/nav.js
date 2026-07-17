// Shared top navigation for the Voice Lab: three isolated game packs, each with a Characters
// view (lab.html) and a Combat Barks view (barks.html). Included by both pages so the chrome is
// identical everywhere. Uses the CSS custom properties both pages already define (--panel/--acc/…).
const GAMES = [
  { id: 'qfg1', name: 'Quest for Glory I', sub: 'So You Want To Be A Hero (EGA)' },
];
function currentGame() {
  const g = new URLSearchParams(location.search).get('game');
  return GAMES.some(x => x.id === g) ? g : 'qfg1';
}
(function injectNavStyles() {
  const css = `
  #topnav{display:flex; align-items:stretch; gap:0; background:var(--panel); border-bottom:1px solid var(--edge); flex:none; height:52px; position:sticky; top:0; z-index:30}
  #topnav .brand{display:flex; flex-direction:column; justify-content:center; padding:0 18px; border-right:1px solid var(--edge)}
  #topnav .brand b{font-size:14px; color:var(--acc); letter-spacing:.02em; line-height:1.1}
  #topnav .brand span{font-size:10.5px; color:var(--dim); letter-spacing:.14em; text-transform:uppercase}
  #topnav .gtabs{display:flex}
  #topnav .gtab{display:flex; flex-direction:column; justify-content:center; padding:0 20px; text-decoration:none;
    color:var(--txt); border-right:1px solid var(--edge); position:relative; min-width:130px}
  #topnav .gtab:hover{background:rgba(255,255,255,.045)}
  #topnav .gtab.on{background:var(--panel2)}
  #topnav .gtab.on:after{content:''; position:absolute; left:0; right:0; bottom:-1px; height:2px; background:var(--acc)}
  #topnav .gtab .gn{font-size:13.5px; font-weight:600; line-height:1.15}
  #topnav .gtab.on .gn{color:var(--acc)}
  #topnav .gtab .gs{font-size:10.5px; color:var(--dim); letter-spacing:.06em}
  /* Characters / Barks view tabs — live at the top of the left sidebar (#sidetabs) */
  #sidetabs{display:flex; border-bottom:1px solid var(--edge)}
  #sidetabs .stab{flex:1; text-align:center; padding:11px 6px; text-decoration:none; color:var(--dim);
    font-weight:600; font-size:13px; border-right:1px solid var(--edge)}
  #sidetabs .stab:last-child{border-right:0}
  #sidetabs .stab:hover{background:rgba(255,255,255,.045); color:var(--txt)}
  #sidetabs .stab.on{color:var(--acc); background:var(--panel2)}
  .incfilter{display:flex; align-items:center; gap:7px; padding:9px 14px; font-size:12.5px; color:var(--dim);
    border-bottom:1px solid var(--edge); cursor:pointer; user-select:none}
  .incfilter input{cursor:pointer}
  `;
  const s = document.createElement('style'); s.textContent = css; document.head.appendChild(s);
})();
// view: 'characters' (lab.html) or 'barks' (barks.html). Switching games preserves the current view.
// The top nav holds the brand + the three game tabs; the Characters/Barks view tabs live in the
// sidebar (renderSideTabs), so both pages share the sidebar+main shell.
function renderNav(view) {
  const g = currentGame();
  const page = view === 'barks' ? 'barks.html' : 'lab.html';
  const el = document.getElementById('topnav');
  if (!el) return;
  const gtabs = GAMES.map(x =>
    `<a class="gtab ${x.id === g ? 'on' : ''}" href="${page}?game=${x.id}">
       <span class="gn">${x.name}</span><span class="gs">${x.sub}</span></a>`).join('');
  el.innerHTML =
    `<div class="brand"><b>agitwo Voice Lab</b><span>AI voices</span></div>
     <div class="gtabs">${gtabs}</div>`;
}

// Characters/Barks tabs at the top of the left sidebar (#sidetabs). Switching games is preserved.
function renderSideTabs(view) {
  const g = currentGame();
  const el = document.getElementById('sidetabs');
  if (!el) return;
  el.innerHTML =
    `<a class="stab on" href="lab.html?game=${g}">🎭 Characters</a>`;
}
