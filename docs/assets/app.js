const state = {
  index:null, months:[], selectedMonth:null,
  availableSources:[], selectedSources:new Set(),
  cache:{}, query:"",
  page:1, pageSize:12,
  currentList:[], currentIdx:-1,
  loadCtl:null,               // AbortController for month data
  loadingMonth:false
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
function debounce(fn, wait=200){
  let t; return (...args)=>{ clearTimeout(t); t=setTimeout(()=>fn(...args), wait); };
}

async function loadIndex(){
  const r = await fetch("./data/index.json",{cache:"no-store"});
  if(!r.ok) throw new Error("index.json not found");
  state.index = await r.json();
  const el=document.getElementById("lastUpdated");
  if(state.index.generated_at){
    try { el.textContent = new Date(state.index.generated_at).toLocaleString("zh-CN",{hour12:false,timeZone:"Asia/Shanghai"}); }
    catch { el.textContent = new Date(state.index.generated_at).toLocaleString("zh-CN",{hour12:false}); }
  }
  state.months = (state.index.months || []).sort();
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
  sel.onchange=()=> switchMonth(sel.value);
}

function setListLoading(on){
  const list = document.getElementById("list");
  list.setAttribute("data-loading", on ? "1" : "0");
  state.loadingMonth = on;
}

async function switchMonth(m){
  if(state.loadingMonth) {
    // 防抖：正在切换就忽略快速重复
  }
  state.selectedMonth = m;
  state.page=1;
  setListLoading(true);
  showSkeleton(Math.min(state.pageSize, 12));
  try{
    await rebuildFilters();
    await renderList();
  }catch(e){
    console.error(e);
    const list=document.getElementById("list");
    list.innerHTML=`<div class="card"><div class="card-body"><div class="card-meta">加载失败，稍后重试</div></div></div>`;
  }finally{
    setListLoading(false);
  }
}

async function loadMonthData(monthKey){
  if(state.cache[monthKey]) return state.cache[monthKey];
  if(state.loadCtl) state.loadCtl.abort();
  const ctl = new AbortController();
  state.loadCtl = ctl;
  const [y,m] = monthKey.split("-");
  const url = `./data/${y}/${m}.json`;
  try{
    const r = await fetch(url, {cache:"no-store", signal: ctl.signal});
    let data = [];
    if(r.ok){
      data = await r.json();
    }else{
      data = []; // 该月暂无数据
    }
    data.sort((a,b)=> (b.published_at||"").localeCompare(a.published_at||""));
    state.cache[monthKey] = data;
    return data;
  }catch(e){
    if(e.name === "AbortError") {
      // 被取消，返回空数组，调用方会再次调用
      return [];
    }
    throw e;
  }
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

function firstImageFromHtml(html){
  try{
    const tmp=document.createElement("div"); tmp.innerHTML=html||"";
    const img=tmp.querySelector("img"); return img? img.getAttribute("src") || "" : "";
  }catch(e){ return ""; }
}

function buildCard(it, idx){
  const div=document.createElement("div");
  div.className="card";
  div.dataset.idx = String(idx);
  const cover = it.cover_image || (it.content_html ? firstImageFromHtml(it.content_html) : "");
  const thumb = cover ? `<div class="card-thumb"><img src="${escapeHtml(cover)}" loading="lazy" decoding="async" alt=""></div>` : `<div class="card-thumb"></div>`;
  div.innerHTML = `
    ${thumb}
    <div class="card-body">
      <h3 class="card-title">${escapeHtml(it.title)}</h3>
      <div class="card-meta">
        <span>${it.author?escapeHtml(it.author)+" · ":""}${escapeHtml(fmtDate(it.published_at))}</span>
        <span class="card-tag">${escapeHtml(it.source)}</span>
      </div>
    </div>
  `;
  return div;
}

async function rebuildFilters(){
  const data = await loadMonthData(state.selectedMonth);
  const set = new Set(data.map(it=>it.source));
  state.availableSources = Array.from(set).sort();
  if(state.selectedSources.size===0) state.selectedSources = new Set(state.availableSources);
  const box=document.getElementById("filters");
  box.innerHTML="";
  const frag=document.createDocumentFragment();
  state.availableSources.forEach(src=>{
    const id="src-"+src.replace(/\W+/g,"");
    const label=document.createElement("label");
    const checked=state.selectedSources.has(src)?"checked":"";
    label.innerHTML=`<input type="checkbox" id="${id}" ${checked}> ${escapeHtml(src)}`;
    label.querySelector("input").addEventListener("change",(e)=>{
      if(e.target.checked) state.selectedSources.add(src); else state.selectedSources.delete(src);
      state.page=1; renderList();
    });
    frag.appendChild(label);
  });
  box.appendChild(frag);
}

function renderPager(total, page, pageSize){
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const info = document.getElementById("pageInfo");
  info.textContent = `${page} / ${pages}`;
  const prev = document.getElementById("prevPage");
  const next = document.getElementById("nextPage");
  prev.disabled = (page<=1);
  next.disabled = (page>=pages);
  prev.onclick = ()=>{ if(state.page>1){ state.page--; renderList(); } };
  next.onclick = ()=>{ if(state.page<pages){ state.page++; renderList(); } };
}

async function renderList(){
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
  list.innerHTML="";

  state.currentList = filtered;
  state.currentIdx = -1;

  const total = filtered.length;
  const pages = Math.max(1, Math.ceil(total / state.pageSize));
  if(state.page>pages) state.page=pages;
  const start = (state.page-1)*state.pageSize;
  const pageItems = filtered.slice(start, start+state.pageSize);

  const frag = document.createDocumentFragment();
  if(pageItems.length===0){
    const empty=document.createElement("div");
    empty.className="card";
    empty.innerHTML=`<div class="card-body"><div class="card-meta">没有结果</div></div>`;
    frag.appendChild(empty);
  } else {
    pageItems.forEach((it, i)=> frag.appendChild(buildCard(it, start+i)));
  }
  list.appendChild(frag);
  renderPager(total, state.page, state.pageSize);
}

/* Reader（全屏大卡片） */
function openReaderByIndex(idx){
  if(idx<0 || idx>=state.currentList.length) return;
  state.currentIdx = idx;
  const it = state.currentList[idx];

  const rd = document.getElementById("reader");
  const title = document.getElementById("rd-title");
  const meta  = document.getElementById("rd-meta");
  const source= document.getElementById("rd-source");
  const stand = document.getElementById("rd-standfirst");
  const heroW = document.getElementById("rd-hero-wrap");
  const hero  = document.getElementById("rd-hero");
  const body  = document.getElementById("rd-body");

  // 先清空，显示轻骨架
  body.innerHTML = `<p class="meta">加载中…</p>`;
  hero.src=""; heroW.hidden=true;

  requestAnimationFrame(()=>{
    title.textContent = it.title || "";
    meta.textContent  = `${it.author?it.author+" · ":""}${fmtDate(it.published_at)} · ${it.source}`;
    source.textContent= it.source || "";
    stand.textContent = it.summary || "";

    const cover = it.cover_image || (it.content_html ? firstImageFromHtml(it.content_html) : "");
    if(cover){ hero.src = cover; hero.loading="lazy"; hero.decoding="async"; heroW.hidden=false; }

    body.innerHTML = "";
    if(it.content_html){
      const tmp=document.createElement("div");
      tmp.innerHTML = it.content_html;
      tmp.querySelectorAll("script,style,noscript").forEach(n=>n.remove());
      body.appendChild(tmp);
    }else if(it.content_text){
      it.content_text.split(/\n{2,}/).forEach(p=>{
        const el=document.createElement("p"); el.textContent=p.trim(); body.appendChild(el);
      });
    }else{
      const p=document.createElement("p");
      p.className="meta"; p.textContent="暂无法站内展示全文，请打开原文查看。";
      const a=document.createElement("a");
      a.href=it.url; a.target="_blank"; a.rel="noopener noreferrer"; a.textContent="原文";
      p.appendChild(document.createTextNode(" "));
      p.appendChild(a);
      body.appendChild(p);
    }
  });

  rd.classList.remove("hidden");
  document.body.style.overflow="hidden";
  updateReaderNav();
}
function closeReader(){
  const rd = document.getElementById("reader");
  rd.classList.add("hidden");
  document.body.style.overflow="";
  state.currentIdx = -1;
}
function updateReaderNav(){
  const prev = document.getElementById("rd-prev");
  const next = document.getElementById("rd-next");
  prev.disabled = (state.currentIdx<=0);
  next.disabled = (state.currentIdx>=state.currentList.length-1);
}
function goReader(delta){
  const idx = state.currentIdx + delta;
  if(idx<0 || idx>=state.currentList.length) return;
  openReaderByIndex(idx);
}

/* 主题 + 键盘 + 事件委托 */
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
function bindKeys(){
  document.addEventListener("keydown", (e)=>{
    const rdOpen = !document.getElementById("reader").classList.contains("hidden");
    if(e.key==="Escape" && rdOpen) closeReader();
    if(rdOpen && (e.key==="ArrowRight"||e.key==="PageDown")) goReader(1);
    if(rdOpen && (e.key==="ArrowLeft" ||e.key==="PageUp"))   goReader(-1);
  }, { passive:true });
}

function bindUI(){
  const list = document.getElementById("list");
  list.addEventListener("click",(e)=>{
    const card = e.target.closest(".card");
    if(!card) return;
    const idx = Number(card.dataset.idx || -1);
    if(idx>=0) openReaderByIndex(idx);
  });

  const onSearch = debounce((e)=>{ state.query = e.target.value || ""; state.page=1; renderList(); }, 200);
  document.getElementById("q").addEventListener("input", onSearch);

  document.getElementById("themeToggle").addEventListener("click", toggleTheme);
  document.getElementById("rd-close").addEventListener("click", closeReader);
  document.getElementById("rd-prev").addEventListener("click", ()=>goReader(-1));
  document.getElementById("rd-next").addEventListener("click", ()=>goReader(1));
  initTheme(); bindKeys();
}

/* 启动 */
(async function(){
  bindUI();
  try{
    await loadIndex();
    await rebuildFilters();
    await renderList();
  }catch(e){
    console.error(e);
    document.getElementById("list").innerHTML=
      `<div class="card"><div class="card-body"><div class="card-meta">数据尚未生成。请先运行 Backfill 或 Daily。</div></div></div>`;
  }
})();
