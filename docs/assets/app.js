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

// 纯描边图标
const ICONS = {
  read: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 5h7a4 4 0 0 1 4 4v10H8a4 4 0 0 0-4 4V5z"/><path d="M11 5h7a4 4 0 0 1 4 4v10h-7"/></svg>`,
  ext:  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 3h7v7"/><path d="M10 14 21 3"/><path d="M21 14v7H3V3h7"/></svg>`,
  search:`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.35-4.35"/></svg>`,
  calendar:`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>`,
  filter:`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 6h16l-6 7v5l-4 2v-7z"/></svg>`,
  back:`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 18l-6-6 6-6"/></svg>`
};

async function loadIndex(){
  const r = await fetch("./data/index.json",{cache:"no-store"});
  if(!r.ok) throw new Error("index.json not found");
  state.index = await r.json();
  const el=document.getElementById("lastUpdated");
  if(state.index.generated_at){
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

/* 构建可翻转卡片 */
function buildCard(it){
  const wrap=document.createElement("div");
  wrap.className="flippable";
  wrap.innerHTML=`
    <div class="flip-inner">
      <div class="flip-face flip-front">
        <h3 class="card-title">${escapeHtml(it.title)}</h3>
        <div class="card-meta">
          <span>${it.author?escapeHtml(it.author)+" · ":""}${escapeHtml(fmtDate(it.published_at))}</span>
          <span class="card-tag">${escapeHtml(it.source)}</span>
        </div>
        <div class="card-actions">
          <a href="#" class="btn-circle" data-action="read" title="阅读">${ICONS.read}</a>
          <a class="btn-circle" href="${it.url}" target="_blank" rel="noopener noreferrer" title="原文">${ICONS.ext}</a>
        </div>
      </div>
      <div class="flip-face flip-back">
        <div class="back-toolbar">
          <button class="btn-circle" data-action="back" title="返回">${ICONS.back}</button>
          <div class="back-meta"></div>
        </div>
        <h4 class="back-title"></h4>
        <div class="back-body"></div>
      </div>
    </div>
  `;

  const front = wrap.querySelector(".flip-front");
  const back  = wrap.querySelector(".flip-back");
  const inner = wrap.querySelector(".flip-inner");
  const title = back.querySelector(".back-title");
  const meta  = back.querySelector(".back-meta");
  const body  = back.querySelector(".back-body");

  title.textContent = it.title || "";
  meta.textContent  = `${it.author?it.author+" · ":""}${fmtDate(it.published_at)} · ${it.source}`;

  // 填充正文（优先 content_html，其次 content_text）
  if(it.content_html){
    const tmp=document.createElement("div");
    tmp.innerHTML=it.content_html;
    // 安全移除 inline script/style 已在后台做，这里兜底
    tmp.querySelectorAll("script,style,noscript").forEach(n=>n.remove());
    body.appendChild(tmp);
  } else if(it.content_text){
    it.content_text.split(/\n{2,}/).forEach(p=>{
      const el=document.createElement("p"); el.textContent=p.trim(); body.appendChild(el);
    });
  } else {
    const p = document.createElement("p");
    p.className="back-meta";
    p.textContent = "暂无法站内展示全文，请打开原文查看。";
    body.appendChild(p);
  }

  // 交互：阅读=翻转；返回=翻回；点击原文按钮放行
  front.querySelector('[data-action="read"]').addEventListener("click",(e)=>{
    e.preventDefault(); wrap.classList.add("flipped");
  });
  back.querySelector('[data-action="back"]').addEventListener("click",(e)=>{
    e.preventDefault(); wrap.classList.remove("flipped");
  });

  return wrap;
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
  list.querySelectorAll(".flippable").forEach(n=>n.remove());
  if(filtered.length===0){
    const empty=document.createElement("div"); empty.className="flippable";
    empty.innerHTML=`<div class="flip-inner"><div class="flip-face flip-front"><div class="card-meta">没有结果</div></div></div>`;
    list.appendChild(empty); return;
  }
  filtered.forEach(it=>list.appendChild(buildCard(it)));
}

/* 主题切换（持久化）与头部阴影 */
function applyTheme(t){
  document.documentElement.setAttribute("data-theme", t);
  const btn = document.getElementById("themeToggle");
  if(btn) btn.textContent = (t === "dark") ? "☀︎" : "🌙";
}
function initTheme(){ applyTheme(localStorage.getItem("theme") || "light"); }
function toggleTheme(){
  const cur = document.documentElement.getAttribute("data-theme") || "light";
  const next = (cur === "dark") ? "light" : "dark";
  localStorage.setItem("theme", next); applyTheme(next);
}
function bindHeaderShadow(){
  const hdr = document.getElementById("hdr");
  const onScroll = ()=>{ if(window.scrollY>6) hdr.classList.add("scrolled"); else hdr.classList.remove("scrolled"); };
  onScroll(); window.addEventListener("scroll", onScroll, { passive:true });
}

/* 控件图标与工具 */
function injectControlIcons(){
  const iconSearch = document.getElementById("iconSearch");
  const iconCalendar = document.getElementById("iconCalendar");
  const filtersToggle = document.getElementById("filtersToggle");
  if(iconSearch)  iconSearch.innerHTML = ICONS.search;
  if(iconCalendar)iconCalendar.innerHTML = ICONS.calendar;
  if(filtersToggle) filtersToggle.innerHTML = ICONS.filter;
}
function bindControlsUtilities(){
  const input = document.getElementById("q");
  const clear = document.getElementById("clearSearch");
  if(clear){
    const updateClear = ()=>{
      const has = !!(input.value && input.value.trim());
      clear.style.opacity = has ? "1" : ".35";
      clear.style.pointerEvents = has ? "auto" : "none";
    };
    input.addEventListener("input", ()=>{ state.query = input.value || ""; updateClear(); renderList(); });
    clear.addEventListener("click",(e)=>{ e.preventDefault(); input.value=""; state.query=""; updateClear(); renderList(); input.focus(); });
    updateClear();
  }
  const toggle = document.getElementById("filtersToggle");
  const filters = document.getElementById("filters");
  if(window.innerWidth < 820) filters.classList.add("collapsed");
  if(toggle){ toggle.addEventListener("click", ()=>{ filters.classList.toggle("collapsed"); }); }
}

function bindUI(){
  const themeBtn = document.getElementById("themeToggle");
  if(themeBtn) themeBtn.addEventListener("click", toggleTheme);
  initTheme();
  bindHeaderShadow();
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
    document.getElementById("list").innerHTML=
      `<div class="flippable"><div class="flip-inner"><div class="flip-face flip-front"><div class="card-meta">数据尚未生成。请先运行 Backfill 或 Daily。</div></div></div></div>`;
  }
})();
