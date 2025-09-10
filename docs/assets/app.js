const state = {
  index:null, months:[], selectedMonth:null,
  availableSources:[], selectedSources:new Set(),
  cache:{}, query:""
};

function escapeHtml(s){
  return (s||"").replace(/[&<>"']/g, m=>({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  }[m]));
}
function fmtDate(iso){
  if(!iso) return "";
  const d=new Date(iso);
  try { return d.toLocaleString("zh-CN",{hour12:false,timeZone:"Asia/Shanghai"}); }
  catch { return d.toLocaleString("zh-CN",{hour12:false}); }
}

// 纯描边黑/白图标（继承 currentColor）
const ICONS = {
  read: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 5h7a4 4 0 0 1 4 4v10H8a4 4 0 0 0-4 4V5z"/><path d="M11 5h7a4 4 0 0 1 4 4v10h-7"/></svg>`,
  ext:  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 3h7v7"/><path d="M10 14 21 3"/><path d="M21 14v7H3V3h7"/></svg>`,
  search:`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.35-4.35"/></svg>`,
  calendar:`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>`,
  filter:`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 6h16l-6 7v5l-4 2v-7z"/></svg>`
};

async function loadIndex(){
  const r = await fetch("./data/index.json",{cache:"no-store"});
  if(!r.ok) throw new Error("index.json not found");
  state.index = await r.json();
  if(state.index.generated_at){
    const el=document.getElementById("lastUpdated");
    try { el.textContent = new Date(state.index.generated_at).toLocaleString("zh-CN",{hour12:false,timeZone:"Asia/Shanghai"}); }
    catch { el.textContent = new Date(state.index.generated_at).toLocaleString("zh-CN",{hour12:false}); }
  }
  state.months = state.index.months || [];
  state.selectedMonth = state.months[state.months.length-1];
  renderMonthOptions();
}

function renderMonthOptions(){
  const sel=document.getElementById("monthSelect");
  sel.innerHTML="";
  state.months.forEach(m=>{
    const opt=document.createElement("option");
    opt.value=m; opt.textContent=`${m} (${state.index.counts[m]||0})`;
    sel.appendChild(opt);
  });
  if(state.selectedMonth) sel.value=state.selectedMonth;
  sel.onchange=async()=>{ state.selectedMonth=sel.value; await rebuildFilters(); renderList(); };
}

async function loadMonthData(monthKey){
  if(state.cache[monthKey]) return state.cache[monthKey];
  const [y,m]=monthKey.split("-");
  const r=await fetch(`./data/${y}/${m}.json`,{cache:"no-store"});
  const data=r.ok? await r.json(): [];
  state.cache[monthKey]=data;
  return data;
}

function showSkeleton(n=10){
  const box=document.getElementById("skeletons");
  box.innerHTML="";
  for(let i=0;i<n;i++){
    const d=document.createElement("div"); d.className="skel";
    d.innerHTML=`<div class="l t"></div><div class="l m"></div><div class="l s"></div>`;
    box.appendChild(d);
  }
}
function hideSkeleton(){ document.getElementById("skeletons").innerHTML=""; }

function buildCard(it){
  const div=document.createElement("div");
  div.className="card";
  div.dataset.id = it.id;

  const by = it.author ? `<span class="byline">${escapeHtml(it.author)}</span>` : "";
  const meta = `
    <span>${by}${by?" · ":""}${escapeHtml(fmtDate(it.published_at))}</span>
    <span class="tag">${escapeHtml(it.source)}</span>
  `;

  const readBtn = `<a href="#" class="btn-circle" data-action="read" title="站内阅读">${ICONS.read}</a>`;
  const openBtn = `<a class="btn-circle" href="${it.url}" target="_blank" rel="noopener noreferrer" title="原文">${ICONS.ext}</a>`;

  div.innerHTML = `
    <h3>${escapeHtml(it.title)}</h3>
    <div class="meta">${meta}</div>
    <div class="summary"></div>
    <div class="actions">${readBtn} ${openBtn}</div>
  `;

  div.addEventListener("click", (e)=>{
    const a = e.target.closest("a");
    if(a && !a.dataset.action) return; // 外链不拦截
    e.preventDefault();
    const hasContent = !!(it.content_html || it.content_text);
    if(hasContent){ openReader(it); }
    else { window.open(it.url, "_blank", "noopener,noreferrer"); }
  });
  return div;
}

async function rebuildFilters(){
  const data = await loadMonthData(state.selectedMonth);
  const set = new Set(data.map(it=>it.source));
  state.availableSources = Array.from(set).sort();
  if(state.selectedSources.size===0) state.selectedSources = new Set(state.availableSources);
  const box=document.getElementById("filters");
  box.innerHTML="";
  state.availableSources.forEach(src=>{
    const id="src-"+src.replace(/\W+/g,"");
    const label=document.createElement("label");
    const checked=state.selectedSources.has(src)?"checked":"";
    label.innerHTML=`<input type="checkbox" id="${id}" ${checked}> ${escapeHtml(src)}`;
    box.appendChild(label);
    label.querySelector("input").addEventListener("change",(e)=>{
      if(e.target.checked) state.selectedSources.add(src); else state.selectedSources.delete(src);
      renderList();
    });
  });
}

async function renderList(){
  showSkeleton(10);
  const list=document.getElementById("list");
  const data=await loadMonthData(state.selectedMonth);
  const q=(state.query||"").trim().toLowerCase();
  const filtered=data
    .filter(it=> state.selectedSources.size===0 || state.selectedSources.has(it.source))
    .filter(it=>{
      if(!q) return true;
      const hay=(it.title+" "+(it.author||"")).toLowerCase();
      return hay.includes(q);
    });
  hideSkeleton();
  list.querySelectorAll(".card").forEach(n=>n.remove());
  if(filtered.length===0){
    const empty=document.createElement("div"); empty.className="card"; empty.innerHTML=`<div class="meta">没有结果</div>`;
    list.appendChild(empty); return;
  }
  filtered.forEach(it=>list.appendChild(buildCard(it)));
}

/* 阅读器 */
function bindReader(){
  const reader=document.getElementById("reader");
  reader.querySelector(".reader__backdrop").addEventListener("click", closeReader);
  reader.querySelector(".reader__close").addEventListener("click", closeReader);
}
function closeReader(){ const r=document.getElementById("reader"); r.classList.add("hidden"); document.body.style.overflow=""; }
function openReader(it){
  const r=document.getElementById("reader");
  r.classList.remove("hidden"); document.body.style.overflow="hidden";
  document.getElementById("rd-title").textContent=it.title||"";
  document.getElementById("rd-meta").textContent=`${it.author?it.author+" · ":""}${fmtDate(it.published_at)} · ${it.source}`;
  const actions=document.getElementById("rd-actions");
  actions.innerHTML=`<a class="btn-circle" href="${it.url}" target="_blank" rel="noopener noreferrer" title="原文">${ICONS.ext}</a>`;
  const body=document.getElementById("rd-body"); body.innerHTML="";
  if(it.content_html){
    const tmp=document.createElement("div");
    tmp.innerHTML=it.content_html;
    tmp.querySelectorAll("script,style,noscript,iframe").forEach(n=>n.remove());
    body.appendChild(tmp);
  } else if(it.content_text){
    it.content_text.split(/\n{2,}/).forEach(p=>{ const el=document.createElement("p"); el.textContent=p.trim(); body.appendChild(el); });
  } else {
    body.innerHTML=`<p class="meta">该页面未提供可公开提取的全文，请点击“原文”。</p>`;
  }
}

/* 主题切换（持久化） */
function applyTheme(t){
  document.documentElement.setAttribute("data-theme", t);
  const btn = document.getElementById("themeToggle");
  if(btn) btn.textContent = (t === "dark") ? "☀︎" : "🌙";
}
function initTheme(){
  const t = localStorage.getItem("theme") || "light";
  applyTheme(t);
}
function toggleTheme(){
  const cur = document.documentElement.getAttribute("data-theme") || "light";
  const next = (cur === "dark") ? "light" : "dark";
  localStorage.setItem("theme", next);
  applyTheme(next);
}

/* Header 阴影随滚动增强 */
function bindHeaderShadow(){
  const hdr = document.getElementById("hdr");
  const onScroll = () => {
    if(window.scrollY > 6) hdr.classList.add("scrolled");
    else hdr.classList.remove("scrolled");
  };
  onScroll();
  window.addEventListener("scroll", onScroll, { passive:true });
}

/* 搜索/清空/图标注入/筛选折叠 */
function injectControlIcons(){
  const iconSearch = document.getElementById("iconSearch");
  const iconCalendar = document.getElementById("iconCalendar");
  const filtersToggle = document.getElementById("filtersToggle");
  if(iconSearch) iconSearch.innerHTML = ICONS.search;
  if(iconCalendar) iconCalendar.innerHTML = ICONS.calendar;
  if(filtersToggle) filtersToggle.innerHTML = ICONS.filter;
}

function bindControlsUtilities(){
  // 清空搜索
  const input = document.getElementById("q");
  const clear = document.getElementById("clearSearch");
  const updateClear = ()=>{
    const has = !!(input.value && input.value.trim());
    clear.style.opacity = has ? "1" : ".35";
    clear.style.pointerEvents = has ? "auto" : "none";
  };
  input.addEventListener("input", ()=>{
    state.query = input.value || "";
    updateClear();
    renderList();
  });
  clear.addEventListener("click", (e)=>{
    e.preventDefault();
    input.value = "";
    state.query = "";
    updateClear();
    renderList();
    input.focus();
  });
  updateClear();

  // 筛选折叠/展开
  const toggle = document.getElementById("filtersToggle");
  const filters = document.getElementById("filters");
  if(window.innerWidth < 820) filters.classList.add("collapsed");
  if(toggle){
    toggle.addEventListener("click", ()=>{
      filters.classList.toggle("collapsed");
    });
  }
}

function bindUI(){
  const themeBtn = document.getElementById("themeToggle");
  if(themeBtn) themeBtn.addEventListener("click", toggleTheme);
  initTheme();
  bindHeaderShadow();
  bindReader();
  injectControlIcons();
  bindControlsUtilities();
}

(async function(){
  bindUI();
  try{
    await loadIndex();
    await rebuildFilters();
    await renderList();
  }catch(e){
    document.getElementById("list").innerHTML=`<div class="card"><div class="meta">数据尚未生成。请先运行 Backfill 或 Daily。</div></div>`;
  }
})();
