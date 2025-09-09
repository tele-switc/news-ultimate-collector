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

// 极简黑色图标
const ICONS = {
  read: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 5h7a4 4 0 0 1 4 4v10H8a4 4 0 0 0-4 4V5z"/><path d="M11 5h7a4 4 0 0 1 4 4v10h-7"/></svg>`,
  ext: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 3h7v7"/><path d="M10 14 21 3"/><path d="M21 14v7H3V3h7"/></svg>`
};

async function loadIndex(){
  const r = await fetch("./data/index.json",{cache:"no-store"});
  if(!r.ok) throw new Error("index.json not found");
  state.index = await r.json();
  const gen = state.index.generated_at;
  if(gen){
    const el=document.getElementById("lastUpdated");
    try { el.textContent = `数据生成于：${new Date(gen).toLocaleString("zh-CN",{hour12:false,timeZone:"Asia/Shanghai"})}`; }
    catch { el.textContent = `数据生成于：${new Date(gen).toLocaleString("zh-CN",{hour12:false})}`; }
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

function showSkeleton(n=12){
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
  const meta = `${by}${by?" · ":""}${escapeHtml(fmtDate(it.published_at))} · ${escapeHtml(it.source)}`;
  const readBtn = `<a href="#" class="btn-circle" data-action="read" title="站内阅读">${ICONS.read}</a>`;
  const openBtn = `<a class="btn-circle" href="${it.url}" target="_blank" rel="noopener noreferrer" title="原文">${ICONS.ext}</a>`;
  div.innerHTML = `
    <h3>${escapeHtml(it.title)}</h3>
    <div class="meta">${meta}</div>
    <div class="summary">${escapeHtml(it.summary||"")}</div>
    <div class="actions">${readBtn} ${openBtn}</div>
  `;
  // 整卡点击打开阅读器；外链按钮不拦截
  div.addEventListener("click", (e)=>{
    const a = e.target.closest("a");
    if(a && !a.dataset.action) return;
    e.preventDefault();
    openReader(it);
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
  showSkeleton(12);
  const list=document.getElementById("list");
  const data=await loadMonthData(state.selectedMonth);
  const q=(state.query||"").trim().toLowerCase();
  const filtered=data
    .filter(it=> state.selectedSources.size===0 || state.selectedSources.has(it.source))
    .filter(it=>{
      if(!q) return true;
      const hay=(it.title+" "+(it.summary||"")+" "+(it.author||"")).toLowerCase();
      return hay.includes(q);
    });
  hideSkeleton();
  list.querySelectorAll(".card").forEach(n=>n.remove());
  if(filtered.length===0){
    const empty=document.createElement("div"); empty.className="card"; empty.innerHTML=`<div class="meta">没有匹配结果</div>`;
    list.appendChild(empty); return;
  }
  filtered.forEach(it=>list.appendChild(buildCard(it)));
}

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
    body.innerHTML=`<p class="meta">该页面未提供可公开提取的全文，请点击“原文”阅读。</p>`;
  }
}

function bindUI(){
  document.getElementById("q").addEventListener("input", e=>{ state.query = e.target.value || ""; renderList(); });
  bindReader();
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
