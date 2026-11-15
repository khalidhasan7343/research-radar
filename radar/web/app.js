/* Research Radar dashboard — no build step, no dependencies. */
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const main = () => $("#main");
const cache = {};
let OV = null;

async function api(path, body) {
  const opt = body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
  const r = await fetch(path, opt);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch (e) {}
    throw new Error(msg);
  }
  return r.json();
}
async function cached(path) { return cache[path] || (cache[path] = await api(path)); }

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const num = (v, d = 2) => v == null || Number.isNaN(v) ? "–" : (Math.abs(v) >= 1000 ? Math.round(v).toLocaleString() : (+v).toFixed(d).replace(/\.?0+$/, "") || "0");
const x100 = (v) => v == null ? "–" : `×${(+v).toFixed(2)}`;

/* ---------- colour ---------- */
const RAMP = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"];
function hexToRgb(h) { const n = parseInt(h.slice(1), 16); return [n >> 16, (n >> 8) & 255, n & 255]; }
function mix(a, b, t) { const A = hexToRgb(a), B = hexToRgb(b); return `rgb(${A.map((v, i) => Math.round(v + (B[i] - v) * t)).join(",")})`; }
function seq(t) { // sequential blue, t in [0,1]
  t = Math.max(0, Math.min(1, t)); const p = t * (RAMP.length - 1), i = Math.min(RAMP.length - 2, Math.floor(p));
  return mix(RAMP[i], RAMP[i + 1], p - i);
}
function diverging(v) { // v in [-1, 1]: negative = red (under-explored), positive = blue
  v = Math.max(-1, Math.min(1, v));
  return v < 0 ? mix("#f0efec", "#e34948", -v) : mix("#f0efec", "#2a78d6", v);
}

const TAG_STATUS = { "sweet spot": "var(--good)", "niche gem": "var(--good)", "rising": "var(--series-1)", "hot & crowded": "var(--serious)",
  "mainstream": "var(--text-muted)", "steady": "var(--text-muted)", "cooling": "var(--critical)" };
const tag = (t) => `<span class="tag"><i style="background:${TAG_STATUS[t] || "var(--text-muted)"}"></i>${esc(t)}</span>`;
const scoreBar = (v) => `<div class="score"><b>${v == null ? "–" : Math.round(v)}</b><div class="bar" style="flex:1"><span style="width:${v || 0}%"></span></div></div>`;
const venueTag = (p) => `${esc((p.venue || "").toUpperCase())} ${p.year || ""}${p.presentation === "oral" || p.presentation === "spotlight" ? ` <span class="pill hl">${p.presentation}</span>` : ""}`;

/* ---------- tooltip ---------- */
const tip = { el: null };
function showTip(html, ev) {
  const t = $("#tip"); t.innerHTML = html; t.style.display = "block";
  const w = t.offsetWidth, h = t.offsetHeight;
  let x = ev.clientX + 14, y = ev.clientY + 14;
  if (x + w > innerWidth - 8) x = ev.clientX - w - 14;
  if (y + h > innerHeight - 8) y = ev.clientY - h - 14;
  t.style.left = x + "px"; t.style.top = y + "px";
}
function hideTip() { $("#tip").style.display = "none"; }

/* ---------- charts ---------- */
function sparkline(series, key = "share", w = 90, h = 26) {
  if (!series || series.length < 2) return "";
  const vals = series.map((d) => d[key]); const mx = Math.max(...vals) || 1;
  const pts = vals.map((v, i) => [2 + (i * (w - 4)) / (vals.length - 1), h - 3 - ((h - 6) * v) / mx]);
  const d = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join("");
  const last = pts[pts.length - 1];
  return `<svg width="${w}" height="${h}" aria-label="trend"><path d="${d}" fill="none" stroke="var(--series-1)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/><circle cx="${last[0]}" cy="${last[1]}" r="2.5" fill="var(--series-1)"/></svg>`;
}

/** Line chart with crosshair + tooltip. series: [{year, value}] ; single series. */
function lineChart(el, data, { label = "", fmt = (v) => num(v, 2), unit = "" } = {}) {
  const W = el.clientWidth || 520, H = 200, m = { l: 44, r: 16, t: 14, b: 26 };
  const xs = data.map((d) => d.x), ys = data.map((d) => d.y);
  const ymax = Math.max(...ys) * 1.15 || 1;
  const X = (i) => m.l + (xs.length === 1 ? (W - m.l - m.r) / 2 : (i * (W - m.l - m.r)) / (xs.length - 1));
  const Y = (v) => H - m.b - (v / ymax) * (H - m.t - m.b);
  const ticks = [0, ymax / 2, ymax].map((v) => `<line x1="${m.l}" x2="${W - m.r}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--grid)"/><text x="${m.l - 6}" y="${Y(v) + 4}" text-anchor="end" font-size="11" fill="var(--text-muted)">${fmt(v)}</text>`).join("");
  const xl = xs.map((x, i) => `<text x="${X(i)}" y="${H - 6}" text-anchor="middle" font-size="11" fill="var(--text-muted)">${x}</text>`).join("");
  const path = ys.map((v, i) => (i ? "L" : "M") + X(i) + " " + Y(v)).join("");
  const dots = ys.map((v, i) => `<circle cx="${X(i)}" cy="${Y(v)}" r="4" fill="var(--series-1)" stroke="var(--surface-1)" stroke-width="2"/>`).join("");
  el.innerHTML = `<svg width="${W}" height="${H}" role="img" aria-label="${esc(label)}">${ticks}${xl}<path d="${path}" fill="none" stroke="var(--series-1)" stroke-width="2" stroke-linejoin="round"/>${dots}<line class="xh" y1="${m.t}" y2="${H - m.b}" stroke="var(--text-muted)" stroke-dasharray="3 3" visibility="hidden"/><rect x="0" y="0" width="${W}" height="${H}" fill="transparent"/></svg>`;
  const svg = el.firstChild, xh = $(".xh", svg);
  svg.addEventListener("pointermove", (ev) => {
    const r = svg.getBoundingClientRect(), px = ev.clientX - r.left;
    let best = 0; xs.forEach((_, i) => { if (Math.abs(X(i) - px) < Math.abs(X(best) - px)) best = i; });
    xh.setAttribute("x1", X(best)); xh.setAttribute("x2", X(best)); xh.setAttribute("visibility", "visible");
    showTip(`<strong>${fmt(ys[best])}${unit}</strong> <span class="muted">${esc(label)}</span><br>${xs[best]}${data[best].note ? "<br>" + esc(data[best].note) : ""}`, ev);
  });
  svg.addEventListener("pointerleave", () => { xh.setAttribute("visibility", "hidden"); hideTip(); });
}

/* ---------- papers ---------- */
function paperList(papers, extra = () => "") {
  if (!papers || !papers.length) return `<p class="muted">None.</p>`;
  return `<ul class="plist">${papers.map((p) => `<li><div class="t" onclick="openPaper('${esc(p.key)}')">${esc(p.title)}</div>
    <div class="m">${venueTag(p)}${p.topic ? ` · ${esc(p.topic)}` : ""}${p.citations != null ? ` · ${p.citations} cites` : ""}${p.similarity != null ? ` · sim ${num(p.similarity, 3)}` : ""}${extra(p)}</div></li>`).join("")}</ul>`;
}
async function openPaper(key) {
  const d = $("#drawer"), b = $("#drawer-body");
  b.innerHTML = `<div class="loading">Loading…</div>`; d.classList.add("open"); d.setAttribute("aria-hidden", "false");
  try {
    const p = await api("/api/paper/" + encodeURIComponent(key));
    b.innerHTML = `<div class="muted small">${venueTag(p)}</div><h2>${esc(p.title)}</h2>
      <p class="small muted">${esc((p.authors || []).join(", "))}</p>
      ${p.topic_label != null ? `<p class="small">Topic: <a href="#/topic/${p.cluster}" onclick="closeDrawer()">${esc(p.topic_label)}</a>${p.margin != null && p.margin < 0.03 && p.topic2_label ? ` — bridges to <a href="#/topic/${p.cluster2}" onclick="closeDrawer()">${esc(p.topic2_label)}</a>` : ""}</p>` : ""}
      ${p.abstract ? `<p>${esc(p.abstract)}</p>` : `<p class="muted">No abstract in the corpus (title-only record).</p>`}
      ${p.open_problems.length ? `<h3>Gaps this paper admits</h3>${p.open_problems.map((s) => `<div class="quote">${esc(s)}</div>`).join("")}` : ""}
      <p class="row">${p.url ? `<a href="${esc(p.url)}" target="_blank" rel="noopener">Open paper ↗</a>` : ""}
      ${p.arxiv_id ? `<a href="https://arxiv.org/abs/${esc(p.arxiv_id)}" target="_blank" rel="noopener">arXiv ↗</a>` : ""}
      <a href="#/lab" onclick="closeDrawer();sessionStorage.setItem('lab', ${esc(JSON.stringify(JSON.stringify(p.title)))})">Find related →</a></p>`;
  } catch (e) { b.innerHTML = `<p class="err">${esc(e.message)}</p>`; }
}
function closeDrawer() { $("#drawer").classList.remove("open"); $("#drawer").setAttribute("aria-hidden", "true"); }
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });

/* ---------- pages ---------- */
const pages = {};

pages[""] = async () => {
  const o = OV;
  if (!o.ready) {
    main().innerHTML = `<h1>Research Radar</h1><div class="card empty"><p><b>No analysis yet.</b></p>
      <p>Add papers, then run the pipeline:</p><pre style="text-align:left;display:inline-block">radar ingest venues --venues neurips,icml,iclr --years 2023-2025
radar analyze
radar serve</pre></div>`; return;
  }
  const ci = o.cluster_info || {}, ti = o.trend_info || {};
  const opps = o.top_opportunity.map((t) => `<tr class="click" onclick="location.hash='#/topic/${t.cluster}'"><td>${esc(t.label)}</td><td>${tag(t.tag)}</td><td class="num">${x100(t.momentum)}</td><td style="width:150px">${scoreBar(t.opportunity)}</td></tr>`).join("");
  const mlist = (arr) => arr.map((t) => `<tr class="click" onclick="location.hash='#/topic/${t.cluster}'"><td>${esc(t.label)}</td><td class="num">${t.competition}</td><td class="num"><b>${x100(t.momentum)}</b></td></tr>`).join("");
  main().innerHTML = `<h1>Overview</h1>
    <p class="sub">${o.n_papers.toLocaleString()} papers · ${ti.first}–${ti.last} · ${o.summary.length ? new Set(o.summary.map((s) => s.venue)).size : 0} venues. Last analysed ${esc(o.last_run || "–")}. Every number here is a measurement; the opportunity score is a weighted judgement whose weights you can change on the <a href="#/topics">Topics</a> page.</p>
    <div class="grid g4" style="margin-bottom:16px">
      <div class="card stat"><div class="v">${o.n_topics}</div><div class="l">topics in ${ci.themes} themes</div></div>
      <div class="card stat"><div class="v">${(o.tags["sweet spot"] || 0) + (o.tags["niche gem"] || 0)}</div><div class="l">“sweet spot” or “niche gem” topics</div></div>
      <div class="card stat"><div class="v">${o.n_open_problems.toLocaleString()}</div><div class="l">admitted open problems extracted</div></div>
      <div class="card stat"><div class="v">${o.n_ideas}</div><div class="l">evidence-backed idea seeds</div></div>
    </div>
    ${whatsNew(o)}
    <div class="grid g2">
      <div class="card"><h2>Highest opportunity</h2><div class="tw"><table><thead><tr><th>Topic</th><th>Signal</th><th class="num">Momentum</th><th>Score</th></tr></thead><tbody>${opps}</tbody></table></div></div>
      <div class="card"><h2>New &amp; rising vocabulary</h2><p class="small muted">Terms whose title frequency in ${ti.last} jumped against earlier years. Click a term to see its curve.</p>
        <div class="chips">${o.new_terms.map((t) => `<span class="chip" onclick="location.hash='#/terms?q=${encodeURIComponent(t.term)}'">${esc(t.term)}<b>${t.status === "new" ? "new" : "z " + num(t.z, 1)}</b></span>`).join("")}</div></div>
      <div class="card"><h2>Fastest growing share</h2><table><thead><tr><th>Topic</th><th class="num">Papers ${ti.last}</th><th class="num">Share ${ti.first}→${ti.last}</th></tr></thead><tbody>${mlist(o.fastest)}</tbody></table></div>
      <div class="card"><h2>Cooling</h2><table><thead><tr><th>Topic</th><th class="num">Papers ${ti.last}</th><th class="num">Share ${ti.first}→${ti.last}</th></tr></thead><tbody>${mlist(o.cooling)}</tbody></table></div>
    </div>
    <p class="small muted" style="margin-top:18px">${ci.ami_vs_official_topics ? `Topic agreement with the venues’ own taxonomy (AMI) ${num(ci.ami_vs_official_topics, 3)}. ` : ""}${ci.title_agreement ? `Title-only papers placed by title (${Math.round(ci.title_agreement * 100)}% agreement with abstract placement); trend counts use title placement for every year.` : ""}</p>`;
};

function whatsNew(o) {
  const ch = o.changes;
  if (!ch || ch.first_run) return "";
  const items = [];
  (ch.new_releases || []).forEach((r) => items.push(`<li><b>New release:</b> ${esc(r.venue.toUpperCase())} ${r.year} — ${r.n.toLocaleString()} papers</li>`));
  (ch.grown || []).slice(0, 4).forEach((r) => items.push(`<li>${esc(r.venue.toUpperCase())} ${r.year}: ${r.before.toLocaleString()} → ${r.n.toLocaleString()} papers</li>`));
  (ch.new_topics || []).slice(0, 4).forEach((t) => items.push(`<li><b>New topic:</b> <a href="#/topic/${t.cluster}">${esc(t.label)}</a> (${t.size} papers)</li>`));
  (ch.movers || []).slice(0, 5).forEach((t) => items.push(`<li><a href="#/topic/${t.cluster}">${esc(t.label)}</a>: opportunity ${Math.round(t.opportunity_before)} → <b>${Math.round(t.opportunity)}</b>${t.tag !== t.tag_before ? `, now ${tag(t.tag)}` : ""}</li>`));
  if ((ch.new_terms || []).length) items.push(`<li><b>New terms:</b> ${ch.new_terms.slice(0, 10).map((x) => `<a href="#/terms?q=${encodeURIComponent(x)}">${esc(x)}</a>`).join(", ")}</li>`);
  const tr = o.tracking && o.tracking.venues && o.tracking.venues.length ? `Tracking ${o.tracking.venues.map((v) => v.toUpperCase()).join(", ")}${o.tracking.arxiv ? " + arXiv" : ""}. ` : "";
  return `<div class="card" style="margin-bottom:16px"><h2>What’s new <span class="muted small" style="font-weight:400">since ${esc(ch.since || "–")} · ${(ch.n_new_papers || 0).toLocaleString()} new papers</span></h2>
    ${items.length ? `<ul style="margin:0;padding-left:18px">${items.join("")}</ul>` : `<p class="muted" style="margin:0">No meaningful changes in the last update (${esc(ch.date)}).</p>`}
    <p class="small muted" style="margin:8px 0 0">${tr}Run <code>radar update</code> (or let the weekly schedule do it) to refresh.</p></div>`;
}

/* ----- landscape map ----- */
pages.map = async () => {
  main().innerHTML = `<h1>Landscape</h1><p class="sub">Every paper with an abstract, placed by meaning (2-D projection of the embeddings). Shade = opportunity score of the paper’s topic. Scroll to zoom, drag to pan, click a dot to read the paper.</p>
    <div class="filters"><label>Theme <select id="m-theme"><option value="">All themes</option></select></label>
    <label>Year <select id="m-year"><option value="">All</option></select></label>
    <label><input type="checkbox" id="m-hl"> Orals &amp; spotlights only</label>
    <label><input type="checkbox" id="m-lab" checked> Topic labels</label>
    <div class="legend" style="margin-left:auto"><span>Opportunity</span><span>low</span><span class="ramp"></span><span>high</span></div></div>
    <div class="mapwrap"><canvas id="map"></canvas></div><div class="loading" id="m-load">Loading points…</div>`;
  const [M, T] = await Promise.all([cached("/api/map"), cached("/api/topics")]);
  $("#m-load").remove();
  const opp = {}; T.topics.forEach((t) => (opp[t.cluster] = t.opportunity));
  const omin = Math.min(...Object.values(opp)), omax = Math.max(...Object.values(opp));
  T.themes.forEach((t) => $("#m-theme").insertAdjacentHTML("beforeend", `<option value="${t.theme}">${esc(t.label)}</option>`));
  [...new Set(M.year)].sort().forEach((y) => $("#m-year").insertAdjacentHTML("beforeend", `<option>${y}</option>`));
  const cv = $("#map"), ctx = cv.getContext("2d");
  const n = M.x.length;
  let xmin = Math.min(...M.x), xmax = Math.max(...M.x), ymin = Math.min(...M.y), ymax = Math.max(...M.y);
  let view = { k: 1, tx: 0, ty: 0 };
  let W, H, dpr, sx = [], sy = [], vis = [];
  const st = { theme: "", year: "", hl: false, labels: true };
  function size() { dpr = devicePixelRatio || 1; W = cv.clientWidth; H = cv.clientHeight; cv.width = W * dpr; cv.height = H * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0); }
  const px = (x) => (24 + ((x - xmin) / (xmax - xmin)) * (W - 48)) * view.k + view.tx;
  const py = (y) => (24 + ((ymax - y) / (ymax - ymin)) * (H - 48)) * view.k + view.ty;
  function draw() {
    ctx.clearRect(0, 0, W, H); sx = new Float32Array(n); sy = new Float32Array(n); vis = new Uint8Array(n);
    const r = Math.max(1.6, Math.min(4, 1.8 * Math.sqrt(view.k)));
    const order = [[], []];
    for (let i = 0; i < n; i++) {
      sx[i] = px(M.x[i]); sy[i] = py(M.y[i]);
      const ok = (!st.year || M.year[i] == st.year) && (!st.hl || M.hl[i]);
      if (!ok) continue; vis[i] = 1;
      order[st.theme === "" || M.t[i] == st.theme ? 1 : 0].push(i);
    }
    ctx.fillStyle = "#dddcd6";
    for (const i of order[0]) { ctx.beginPath(); ctx.arc(sx[i], sy[i], r * 0.8, 0, 7); ctx.fill(); }
    for (const i of order[1]) {
      ctx.fillStyle = seq(0.12 + 0.88 * (opp[M.c[i]] - omin) / (omax - omin || 1));
      ctx.beginPath(); ctx.arc(sx[i], sy[i], M.hl[i] ? r + 1.2 : r, 0, 7); ctx.fill();
    }
    if (st.labels) {
      ctx.font = "600 11.5px system-ui, sans-serif"; ctx.textAlign = "center"; const boxes = [];
      const labs = M.labels.filter((l) => l.cx != null && (st.theme === "" || l.theme == st.theme)).sort((a, b) => b.size - a.size);
      for (const l of labs) {
        const x = px(l.cx), y = py(l.cy), w = ctx.measureText(l.label).width + 10, b = [x - w / 2, y - 9, x + w / 2, y + 9];
        if (x < 0 || x > W || y < 0 || y > H || boxes.some((o) => !(b[2] < o[0] || b[0] > o[2] || b[3] < o[1] || b[1] > o[3]))) continue;
        boxes.push(b); ctx.fillStyle = "rgba(252,252,251,.88)"; ctx.fillRect(b[0], b[1], w, 18);
        ctx.fillStyle = "#0b0b0b"; ctx.fillText(l.label, x, y + 4);
      }
    }
  }
  function nearest(mx, my) {
    let best = -1, bd = 100;
    for (let i = 0; i < n; i++) { if (!vis[i]) continue; const d = (sx[i] - mx) ** 2 + (sy[i] - my) ** 2; if (d < bd) { bd = d; best = i; } }
    return best;
  }
  const lab = {}; M.labels.forEach((l) => (lab[l.cluster] = l.label));
  let drag = null;
  cv.addEventListener("pointerdown", (e) => { drag = { x: e.clientX, y: e.clientY, tx: view.tx, ty: view.ty, moved: false }; cv.setPointerCapture(e.pointerId); });
  cv.addEventListener("pointermove", (e) => {
    const r = cv.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
    if (drag) { const dx = e.clientX - drag.x, dy = e.clientY - drag.y; if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true; view.tx = drag.tx + dx; view.ty = drag.ty + dy; draw(); return; }
    const i = nearest(mx, my);
    if (i < 0) return hideTip();
    showTip(`<strong>${esc(M.title[i])}</strong><br><span class="muted">${M.year[i]}${M.hl[i] ? " · oral/spotlight" : ""} · ${esc(lab[M.c[i]])}<br>topic opportunity ${Math.round(opp[M.c[i]])}</span>`, e);
  });
  cv.addEventListener("pointerup", (e) => {
    const was = drag && drag.moved; drag = null; if (was) return;
    const r = cv.getBoundingClientRect(), i = nearest(e.clientX - r.left, e.clientY - r.top); if (i >= 0) { hideTip(); openPaper(M.key[i]); }
  });
  cv.addEventListener("pointerleave", hideTip);
  cv.addEventListener("wheel", (e) => {
    e.preventDefault(); const r = cv.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
    const f = e.deltaY < 0 ? 1.2 : 1 / 1.2, k = Math.max(1, Math.min(30, view.k * f)), g = k / view.k;
    view.tx = mx - (mx - view.tx) * g; view.ty = my - (my - view.ty) * g; view.k = k; if (k === 1) { view.tx = 0; view.ty = 0; } draw();
  }, { passive: false });
  $("#m-theme").onchange = (e) => { st.theme = e.target.value; draw(); };
  $("#m-year").onchange = (e) => { st.year = e.target.value; draw(); };
  $("#m-hl").onchange = (e) => { st.hl = e.target.checked; draw(); };
  $("#m-lab").onchange = (e) => { st.labels = e.target.checked; draw(); };
  size(); draw(); window.onresize = () => { if (location.hash.startsWith("#/map")) { size(); draw(); } };
};

/* ----- topics table with live weights ----- */
const COLS = [
  ["label", "Topic", false], ["tag", "Signal", false], ["competition", "Papers (last yr)", true], ["momentum", "Momentum", true],
  ["recent_growth", "Last-yr growth", true], ["reward_lift", "Reward lift", true], ["impact", "Impact", true], ["openness", "Openness", true],
  ["entry_cost_label", "Entry cost", false], ["concentration", "Repeat-author share", true], ["arxiv_lead", "arXiv lead", true], ["opportunity", "Opportunity", true],
];
const WEIGHT_HELP = { momentum: "share growth", acceleration: "growth speeding up", reward: "oral/spotlight lift", impact: "citations", openness: "admitted open problems",
  low_competition: "fewer papers", low_entry_cost: "less compute", low_concentration: "fewer repeat authors" };
pages.topics = async () => {
  const T = await cached("/api/topics");
  const w = { ...(OV.weights || {}) };
  const st = { sort: "opportunity", dir: -1, theme: "", tag: "", q: "" };
  const hasCol = (c) => T.topics.some((t) => t[c] != null);
  const cols = COLS.filter(([c]) => hasCol(c));
  main().innerHTML = `<h1>Topics &amp; scores</h1><p class="sub">${T.topics.length} topics. Momentum = share of all papers in the latest year ÷ share in the first year. Reward lift = oral/spotlight rate ÷ the rate the topic’s venue mix predicts. Openness = share of abstracts admitting an open problem. Drag the weights to re-rank live.</p>
    <details class="card" style="margin-bottom:14px" open><summary>Opportunity weights</summary><div class="weights">${Object.keys(w).map((k) => `<div><label><span>${k.replace(/_/g, " ")} <span class="muted">· ${WEIGHT_HELP[k] || ""}</span></span><b id="wv-${k}">${w[k]}</b></label><input type="range" min="0" max="2" step="0.25" value="${w[k]}" data-w="${k}"></div>`).join("")}</div></details>
    <div class="filters"><input type="search" id="t-q" placeholder="Filter topics…"><label>Theme <select id="t-theme"><option value="">All</option>${T.themes.map((t) => `<option value="${t.theme}">${esc(t.label)}</option>`).join("")}</select></label>
    <label>Signal <select id="t-tag"><option value="">All</option>${[...new Set(T.topics.map((t) => t.tag))].map((t) => `<option>${esc(t)}</option>`).join("")}</select></label></div>
    <div class="card tw"><table id="t-table"></table></div>`;
  const series = T.series;
  function render() {
    let rows = T.topics.filter((t) => (st.theme === "" || t.theme == st.theme) && (!st.tag || t.tag === st.tag) && (!st.q || t.label.toLowerCase().includes(st.q) || (t.keywords || []).join(" ").includes(st.q)));
    rows.sort((a, b) => { const A = a[st.sort], B = b[st.sort]; if (A == null) return 1; if (B == null) return -1; return (A > B ? 1 : A < B ? -1 : 0) * st.dir; });
    $("#t-table").innerHTML = `<thead><tr>${cols.map(([c, l, n]) => `<th class="sortable ${n ? "num" : ""}" data-c="${c}">${l}${st.sort === c ? (st.dir < 0 ? " ↓" : " ↑") : ""}</th>`).join("")}<th>Share trend</th></tr></thead><tbody>${rows.map((t) => `<tr class="click" onclick="location.hash='#/topic/${t.cluster}'">${cols.map(([c, , n]) => {
      const v = t[c];
      if (c === "label") return `<td style="min-width:210px"><b style="font-weight:550">${esc(v)}</b></td>`;
      if (c === "tag") return `<td>${tag(v)}</td>`;
      if (c === "opportunity") return `<td style="min-width:130px">${scoreBar(v)}</td>`;
      if (c === "momentum" || c === "recent_growth" || c === "reward_lift" || c === "arxiv_lead") return `<td class="num">${x100(v)}</td>`;
      if (c === "openness" || c === "concentration") return `<td class="num">${v == null ? "–" : Math.round(v * 100) + "%"}</td>`;
      return `<td class="${n ? "num" : ""}">${n ? num(v, 1) : esc(v)}</td>`;
    }).join("")}<td>${sparkline(series[t.cluster])}</td></tr>`).join("")}</tbody>`;
    document.querySelectorAll("#t-table th.sortable").forEach((th) => th.onclick = () => { const c = th.dataset.c; st.dir = st.sort === c ? -st.dir : -1; st.sort = c; render(); });
  }
  let pending;
  document.querySelectorAll("[data-w]").forEach((inp) => inp.oninput = () => {
    w[inp.dataset.w] = +inp.value; $("#wv-" + inp.dataset.w).textContent = inp.value;
    clearTimeout(pending); pending = setTimeout(async () => {
      const res = await api("/api/rescore", { weights: w }); const m = {}; res.forEach((r) => (m[r.cluster] = r.opportunity));
      T.topics.forEach((t) => (t.opportunity = m[t.cluster])); render();
    }, 150);
  });
  $("#t-q").oninput = (e) => { st.q = e.target.value.toLowerCase(); render(); };
  $("#t-theme").onchange = (e) => { st.theme = e.target.value; render(); };
  $("#t-tag").onchange = (e) => { st.tag = e.target.value; render(); };
  render();
};

/* ----- topic detail ----- */
pages.topic = async (id) => {
  const D = await api("/api/topics/" + id);
  const m = D.metrics, c = D.cluster, ti = OV.trend_info || {};
  const tile = (v, l) => `<div class="card stat"><div class="v">${v}</div><div class="l">${l}</div></div>`;
  main().innerHTML = `<div class="small muted"><a href="#/topics">Topics</a> ›</div><h1>${esc(m.label)}</h1>
    <p class="sub">${c.summary ? esc(c.summary) + " " : ""}<span class="muted">Keywords: ${esc((c.keywords || []).join(", "))}</span></p>
    <div class="grid g4" style="margin-bottom:16px">${tile(scoreBar(m.opportunity).replace('class="score"', 'class="score" style="font-size:20px"'), "opportunity · " + m.tag)}
    ${tile(x100(m.momentum), `share growth ${ti.first}→${ti.last}`)}${tile(m.competition, `papers in ${ti.last}`)}${tile(x100(m.reward_lift), "oral/spotlight lift")}
    ${tile(m.openness == null ? "–" : Math.round(m.openness * 100) + "%", "abstracts admitting a gap")}${tile(esc(m.entry_cost_label), "entry cost (from abstract language)")}
    ${tile(m.forecast_n == null ? "–" : "~" + m.forecast_n, `projected papers next year (log-linear, same venues)`)}${tile(m.concentration == null ? "–" : Math.round(m.concentration * 100) + "%", "papers with a repeat author")}</div>
    <div class="grid g2" style="margin-bottom:16px"><div class="card"><h2>Share of papers per year</h2><div id="tchart"></div><p class="small muted">Percent of all papers at the venues present every year.</p></div>
    <div class="card"><h2>Neighbouring topics</h2><ul class="plist">${D.neighbours.map((n) => `<li><a href="#/topic/${n.cluster}">${esc(n.label)}</a> <span class="muted small">sim ${n.similarity}</span></li>`).join("")}</ul>
    <h3>Most active authors (recent)</h3><div class="chips">${D.top_authors.map((a) => `<span class="chip">${esc(a.name)}<b>${a.n}</b></span>`).join("")}</div></div></div>
    <div class="card"><div class="tabs" id="ttabs">${["Papers", `Open problems (${D.n_open_problems})`, `Position claims (${D.claims.length})`, `Bridge papers (${D.bridge_papers.length})`, "Reading list"].map((t, i) => `<button data-i="${i}" class="${i ? "" : "on"}">${t}</button>`).join("")}</div><div id="tbody"></div></div>`;
  lineChart($("#tchart"), D.series.map((s) => ({ x: s.year, y: s.share, note: `${s.n} papers` })), { label: "share of papers", unit: "%" });
  const P = D.papers;
  const views = [
    () => `<div class="row" style="margin-bottom:8px">${["central", "highlighted", "cited", "recent"].filter((k) => P[k].length).map((k, i) => `<button class="ghost" data-p="${k}">${k}</button>`).join("")}</div><div id="plist">${paperList(P.central)}</div>`,
    () => D.open_problems.map((o) => `<div class="quote">${esc(o.sentence)}<div class="src">${esc(o.kind.replace("_", " "))} · <a href="javascript:openPaper('${esc(o.key)}')">${esc(o.title)}</a> (${o.year})</div></div>`).join("") || `<p class="muted">None extracted.</p>`,
    () => D.claims.map((o) => `<div class="quote">${esc(o.claim)}<div class="src"><a href="javascript:openPaper('${esc(o.key)}')">${esc(o.title)}</a></div></div>`).join("") || `<p class="muted">No position papers in this topic.</p>`,
    () => `<p class="small muted">Papers that sit almost equally between this topic and another — where topics are already starting to merge.</p>` + paperList(D.bridge_papers, (p) => ` · ↔ ${esc(p.other_topic)}`),
    () => `<div id="rl" class="loading">Building reading list…</div>`,
  ];
  const tabs = document.querySelectorAll("#ttabs button");
  tabs.forEach((b) => b.onclick = async () => {
    tabs.forEach((x) => x.classList.toggle("on", x === b)); $("#tbody").innerHTML = views[+b.dataset.i]();
    document.querySelectorAll("[data-p]").forEach((x) => x.onclick = () => ($("#plist").innerHTML = paperList(P[x.dataset.p])));
    if (b.dataset.i === "4") { const r = await api("/api/reading", { cluster: +id }); $("#rl").outerHTML = readingHTML(r); }
  });
  tabs[0].click();
};
const readingHTML = (r) => Object.entries(r.tiers).map(([t, ps]) => `<h3>${esc(t)}</h3>${paperList(ps)}`).join("");

/* ----- terms ----- */
pages.terms = async (_, params) => {
  const terms = await cached("/api/terms"); const ti = OV.trend_info || {};
  const years = ti.years || [];
  const row = (t) => `<tr class="click" data-term="${esc(t.term)}"><td><b style="font-weight:550">${esc(t.term)}</b></td><td>${t.status === "new" ? '<span class="pill hl">new</span>' : esc(t.status)}</td><td class="num">${num(t.z, 1)}</td>${years.map((y) => `<td class="num">${t.counts[y] ?? 0}</td>`).join("")}<td>${sparkline(years.map((y) => ({ v: t.per_1000[y] || 0 })), "v", 70, 22)}</td></tr>`;
  const head = `<thead><tr><th>Term</th><th>Status</th><th class="num">z</th>${years.map((y) => `<th class="num">${y}</th>`).join("")}<th>per 1k papers</th></tr></thead>`;
  main().innerHTML = `<h1>Emerging terms</h1><p class="sub">Words and phrases in titles, latest year vs all earlier years, scored with the log-odds ratio with an informative Dirichlet prior (so rare words are not over-rewarded). Look up any term below.</p>
    <div class="card" style="margin-bottom:16px"><div class="row"><input type="search" id="tq" placeholder="e.g. world model, test-time, mamba" style="flex:1;max-width:420px"><button id="tgo">Plot</button></div><div id="tplot" style="margin-top:10px"></div></div>
    <div class="grid g2"><div class="card tw"><h2>Rising &amp; new</h2><table>${head}<tbody>${terms.filter((t) => t.status !== "fading").map(row).join("")}</tbody></table></div>
    <div class="card tw"><h2>Fading</h2><table>${head}<tbody>${terms.filter((t) => t.status === "fading").map(row).join("")}</tbody></table></div></div>`;
  async function plot(q) {
    $("#tq").value = q; $("#tplot").innerHTML = `<div class="loading">…</div>`;
    const s = await api("/api/term?q=" + encodeURIComponent(q));
    const data = Object.entries(s).map(([y, v]) => ({ x: y, y: v.per_1000, note: `${v.n} titles` }));
    $("#tplot").innerHTML = `<div class="small muted">“${esc(q)}” — titles per 1,000 papers</div><div id="tp2"></div>`;
    lineChart($("#tp2"), data, { label: `titles per 1k with “${q}”` });
  }
  $("#tgo").onclick = () => $("#tq").value && plot($("#tq").value);
  $("#tq").onkeydown = (e) => e.key === "Enter" && $("#tq").value && plot($("#tq").value);
  document.querySelectorAll("[data-term]").forEach((r) => r.onclick = () => { plot(r.dataset.term); scrollTo({ top: 0, behavior: "smooth" }); });
  if (params.get("q")) plot(params.get("q"));
};

/* ----- gaps ----- */
pages.gaps = async () => {
  const G = await cached("/api/gaps");
  const methods = G.observed.map((r) => r.method);
  const domains = G.observed.length ? Object.keys(G.observed[0]).filter((k) => k !== "method") : [];
  const E = {}; G.expected.forEach((r) => (E[r.method] = r));
  // Colour = log ratio, damped by evidence: a cell expecting 2 papers cannot be as "red" as one expecting 40.
  const cell = (m, d, o) => { const e = E[m][d]; const v = (Math.log2((o + 0.5) / (e + 0.5)) / 3) * Math.min(1, Math.sqrt(e / 12)); return { o, e, v }; };
  const heat = `<table class="heat"><thead><tr><th></th>${domains.map((d) => `<th class="rot"><div>${esc(d)}</div></th>`).join("")}</tr></thead><tbody>${G.observed.map((r) => `<tr><th class="rowh">${esc(r.method)}</th>${domains.map((d) => {
    const c = cell(r.method, d, r[d]); const strong = Math.abs(c.v) > 0.55;
    return `<td data-m="${esc(r.method)}" data-d="${esc(d)}" data-o="${c.o}" data-e="${c.e}" style="background:${c.e < 2 && c.o === 0 ? "var(--surface-1)" : diverging(c.v)};color:${strong ? "#fff" : "var(--text-secondary)"}">${c.e >= 2 || c.o ? c.o : ""}</td>`;
  }).join("")}</tr>`).join("")}</tbody></table>`;
  main().innerHTML = `<h1>Gaps &amp; transplants</h1><p class="sub">Three kinds of gap: method × domain combinations far rarer than their popularity predicts, neighbouring topics that rarely meet, and what papers themselves admit is unsolved.</p>
    <div class="card" style="margin-bottom:16px"><h2>Method × domain</h2><div class="legend" style="margin-bottom:8px"><span>Observed ÷ expected:</span><span style="display:inline-block;width:160px;height:8px;border-radius:4px;background:linear-gradient(90deg,#e34948,#f0efec,#2a78d6)"></span><span>red = under-explored · grey = as expected · blue = well covered. Number = papers. Click a cell to test it as an idea.</span></div><div class="tw">${heat}</div></div>
    <div class="grid g2" style="margin-bottom:16px"><div class="card tw"><h2>Biggest untried combinations</h2><table><thead><tr><th>Method</th><th>Domain</th><th class="num">Observed</th><th class="num">Expected</th><th class="num">Method growth</th></tr></thead><tbody>${G.transplants.filter((t) => t.observed <= t.expected * 0.4).slice(0, 18).map((t) => `<tr class="click" data-idea="${esc(t.method + " for " + t.domain)}"><td>${esc(t.method)}</td><td>${esc(t.domain)}</td><td class="num">${t.observed}</td><td class="num">${num(t.expected, 0)}</td><td class="num">${x100(t.method_growth)}</td></tr>`).join("")}</tbody></table></div>
    <div class="card tw"><h2>Under-connected neighbours</h2><p class="small muted">Topics close in meaning that share fewer in-between papers than expected.</p><table><thead><tr><th>Topic A</th><th>Topic B</th><th class="num">Sim</th><th class="num">Bridges</th><th class="num">Expected</th></tr></thead><tbody>${G.bridges.slice(0, 15).map((b) => `<tr><td><a href="#/topic/${b.a}">${esc(b.label_a)}</a></td><td><a href="#/topic/${b.b}">${esc(b.label_b)}</a></td><td class="num">${b.similarity}</td><td class="num">${b.n_bridge}</td><td class="num">${num(b.expected, 0)}</td></tr>`).join("")}</tbody></table></div></div>
    <div class="card" style="margin-bottom:16px"><h2>Admitted open problems</h2><div class="filters"><input type="search" id="op-q" placeholder="Search sentences, e.g. evaluation, long context" style="flex:1;max-width:420px"><select id="op-k"><option value="">All kinds</option>${Object.entries(G.open_problem_kinds).map(([k, v]) => `<option value="${k}">${k.replace("_", " ")} (${v})</option>`).join("")}</select></div><div id="op-list"></div><button class="ghost" id="op-more">Show more</button></div>
    <div class="card"><h2>What position papers argue (${G.claims.length})</h2><div id="claims"></div><button class="ghost" id="cl-more">Show more</button></div>`;
  let nClaims = 0;
  const moreClaims = () => { $("#claims").insertAdjacentHTML("beforeend", G.claims.slice(nClaims, nClaims + 12).map((c) => `<div class="quote">${esc(c.claim)}<div class="src"><a href="javascript:openPaper('${esc(c.key)}')">${esc(c.title)}</a></div></div>`).join("")); nClaims += 12; $("#cl-more").style.display = nClaims >= G.claims.length ? "none" : ""; };
  $("#cl-more").onclick = moreClaims; moreClaims();
  document.querySelectorAll(".heat td").forEach((td) => {
    td.onpointermove = (e) => showTip(`<strong>${td.dataset.o} papers</strong> vs ${td.dataset.e} expected<br>${esc(td.dataset.m)} × ${esc(td.dataset.d)}`, e);
    td.onpointerleave = hideTip;
    td.onclick = () => goLab(`${td.dataset.m} for ${td.dataset.d}`);
  });
  document.querySelectorAll("[data-idea]").forEach((r) => r.onclick = () => goLab(r.dataset.idea));
  let opLimit = 15;
  $("#op-more").onclick = () => { opLimit += 30; loadOps(); };
  async function loadOps() {
    const r = await api(`/api/open_problems?q=${encodeURIComponent($("#op-q").value)}&kind=${$("#op-k").value}&limit=${opLimit + 1}`);
    $("#op-more").style.display = r.items.length > opLimit ? "" : "none"; r.items = r.items.slice(0, opLimit);
    $("#op-list").innerHTML = r.items.map((o) => `<div class="quote">${esc(o.sentence)}<div class="src">${esc(o.kind.replace("_", " "))} · <a href="#/topic/${o.cluster}">${esc(o.topic)}</a> · <a href="javascript:openPaper('${esc(o.key)}')">${esc(o.title)}</a></div></div>`).join("") || `<p class="muted">Nothing matches.</p>`;
  }
  let t; $("#op-q").oninput = () => { opLimit = 15; clearTimeout(t); t = setTimeout(loadOps, 250); }; $("#op-k").onchange = () => { opLimit = 15; loadOps(); }; loadOps();
};
function goLab(text) { sessionStorage.setItem("lab", JSON.stringify(text)); location.hash = "#/lab"; }

/* ----- ideas ----- */
pages.ideas = async () => {
  const ideas = await cached("/api/ideas");
  const llm = OV.llm.enabled;
  main().innerHTML = `<h1>Idea seeds</h1><p class="sub">Generated from the measurements, never from taste: untried method × domain pairs, admitted gaps in high-opportunity topics, under-connected neighbours, and rising topics that are cheap to enter. Novelty compares each seed’s nearest paper with how close a typical paper sits to its own nearest neighbour (100 = emptiest).${llm ? ` <b>Refine</b> asks ${esc(OV.llm.model)} for a research question, hypothesis and killing experiment.` : ` Connect a free local LLM (Ollama) to turn seeds into research questions — see the README.`}</p>
    <div class="filters"><label>Kind <select id="i-k"><option value="">All</option>${[...new Set(ideas.map((i) => i.kind))].map((k) => `<option>${esc(k)}</option>`).join("")}</select></label></div>
    <div class="grid g3" id="ideas"></div>`;
  function render() {
    const k = $("#i-k").value;
    $("#ideas").innerHTML = ideas.filter((i) => !k || i.kind === k).map((i) => `<div class="card idea"><div class="k">${esc(i.kind)}</div><h4>${esc(i.title)}</h4><p>${esc(i.rationale)}</p>
      <div class="score small"><span class="muted">novelty</span><div class="bar" style="flex:1"><span style="width:${i.novelty}%"></span></div><b>${Math.round(i.novelty)}</b></div>
      ${i.nearest_papers.length ? `<div class="small muted">Closest: <a href="javascript:openPaper('${esc(i.nearest_papers[0].key)}')">${esc(i.nearest_papers[0].title)}</a></div>` : ""}
      <div class="row" style="margin-top:auto">${llm ? `<button data-refine="${i.idea_id}">Refine</button>` : ""}<button class="ghost" data-lab="${i.idea_id}">Open in lab</button>${i.cluster >= 0 ? `<a class="small" href="#/topic/${i.cluster}">topic →</a>` : ""}</div><div id="ref-${i.idea_id}"></div></div>`).join("");
    document.querySelectorAll("[data-lab]").forEach((b) => b.onclick = () => { const i = ideas.find((x) => x.idea_id == b.dataset.lab); goLab(i.title); });
    document.querySelectorAll("[data-refine]").forEach((b) => b.onclick = async () => {
      const i = ideas.find((x) => x.idea_id == b.dataset.refine), box = $("#ref-" + i.idea_id);
      b.disabled = true; box.innerHTML = `<div class="loading">Thinking…</div>`;
      try { const r = await api("/api/ideas/refine", { title: i.title, rationale: i.rationale }); box.innerHTML = refinedHTML(r); }
      catch (e) { box.innerHTML = `<p class="err">${esc(e.message)}</p>`; }
      b.disabled = false;
    });
  }
  $("#i-k").onchange = render; render();
};
function refinedHTML(r) {
  if (r.error) return `<p class="err small">${esc(r.error)}</p>`;
  const f = r.refined || {};
  const lab = { research_question: "Research question", hypothesis: "Hypothesis", killing_experiment: "Killing experiment", first_week_plan: "First week", risk: "Main risk", differentiation: "How to differ", verdict: "Verdict" };
  return `<dl class="refined">${Object.entries(lab).filter(([k]) => f[k]).map(([k, l]) => `<dt>${l}</dt><dd>${Array.isArray(f[k]) ? f[k].map(esc).join("<br>") : esc(f[k])}</dd>`).join("")}</dl>`;
}

/* ----- idea lab ----- */
pages.lab = async () => {
  const pre = JSON.parse(sessionStorage.getItem("lab") || '""'); sessionStorage.removeItem("lab");
  main().innerHTML = `<h1>Idea lab</h1><p class="sub">Describe an idea in a sentence or two. You get how crowded its neighbourhood is, which topics it lands in and how they are trending, the closest existing papers, nearby open problems, and a tiered reading list.</p>
    <div class="card" style="margin-bottom:16px"><textarea id="lab-t" placeholder="e.g. Use reinforcement learning with verifiable rewards to train time-series forecasting models, rewarding calibrated probabilistic forecasts.">${esc(pre)}</textarea>
    <div class="row" style="margin-top:10px"><button id="lab-go">Check idea</button><button class="ghost" id="lab-rl">Reading list</button>${OV.llm.enabled ? `<button class="ghost" id="lab-ref">Refine with LLM</button>` : ""}</div></div><div id="lab-out"></div>`;
  const go = async () => {
    const text = $("#lab-t").value.trim(); if (!text) return;
    $("#lab-out").innerHTML = `<div class="loading">Searching ${OV.n_papers.toLocaleString()} papers…</div>`;
    try {
      const n = await api("/api/novelty", { text, k: 20 });
      $("#lab-out").innerHTML = `<div class="grid g3" style="margin-bottom:16px"><div class="card stat"><div class="v">${Math.round(n.novelty)}<span class="muted" style="font-size:16px">/100</span></div><div class="l">novelty — ${esc(n.verdict)}</div></div>
        <div class="card stat"><div class="v">${num(n.best_similarity, 3)}</div><div class="l">similarity to the closest paper</div></div>
        <div class="card"><div class="small muted">Lands in</div>${n.clusters.map((c) => `<div style="margin:4px 0"><a href="#/topic/${c.cluster}">${esc(c.label)}</a> ${tag(c.tag)} <span class="small muted">momentum ${x100(c.momentum)} · ${c.competition} papers</span></div>`).join("")}</div></div>
        <div class="grid g2"><div class="card"><h2>Closest existing papers</h2>${paperList(n.neighbours)}</div>
        <div class="card"><h2>Open problems nearby</h2>${n.open_problems.map((o) => `<div class="quote">${esc(o.sentence)}<div class="src"><a href="javascript:openPaper('${esc(o.key)}')">${esc(o.title)}</a></div></div>`).join("") || '<p class="muted">None found.</p>'}</div></div>`;
    } catch (e) { $("#lab-out").innerHTML = `<p class="err">${esc(e.message)}</p>`; }
  };
  $("#lab-go").onclick = go;
  $("#lab-rl").onclick = async () => {
    const text = $("#lab-t").value.trim(); if (!text) return; $("#lab-out").innerHTML = `<div class="loading">Building reading list…</div>`;
    const r = await api("/api/reading", { text }); $("#lab-out").innerHTML = `<div class="card"><p class="small muted">Topics: ${r.clusters.map((c) => `<a href="#/topic/${c.cluster}">${esc(c.label)}</a>`).join(", ")}</p>${readingHTML(r)}</div>`;
  };
  if ($("#lab-ref")) $("#lab-ref").onclick = async () => {
    const text = $("#lab-t").value.trim(); if (!text) return; $("#lab-out").innerHTML = `<div class="loading">Thinking…</div>`;
    const r = await api("/api/ideas/refine", { title: text, rationale: "" }); $("#lab-out").innerHTML = `<div class="card">${refinedHTML(r)}</div>`;
  };
  if (pre) go();
};

/* ----- search ----- */
pages.search = async (_, params) => {
  main().innerHTML = `<h1>Search</h1><p class="sub">Semantic search over every paper with an abstract.</p><div class="card" style="margin-bottom:16px"><div class="row"><input type="search" id="sq" style="flex:1" placeholder="e.g. calibration of LLM judges"><button id="sgo">Search</button></div></div><div class="card" id="sres"><p class="muted">Results appear here.</p></div>`;
  const run = async () => { const q = $("#sq").value.trim(); if (!q) return; $("#sres").innerHTML = `<div class="loading">…</div>`; $("#sres").innerHTML = paperList(await api("/api/search?k=40&q=" + encodeURIComponent(q))); };
  $("#sgo").onclick = run; $("#sq").onkeydown = (e) => e.key === "Enter" && run();
  if (params.get("q")) { $("#sq").value = params.get("q"); run(); }
};

/* ---------- router ---------- */
async function route() {
  hideTip(); closeDrawer();
  const h = location.hash.replace(/^#\/?/, ""); const [path, qs] = h.split("?");
  const [name, arg] = path.split("/");
  document.querySelectorAll("nav a").forEach((a) => a.classList.toggle("on", a.dataset.r === (name === "topic" ? "topics" : name)));
  main().innerHTML = `<div class="loading">Loading…</div>`;
  try {
    if (!OV) OV = await api("/api/overview");
    $("#side-foot").innerHTML = `${OV.n_papers.toLocaleString()} papers<br>${OV.llm.enabled ? "LLM: " + esc(OV.llm.model) : "LLM: off"}`;
    if (!OV.ready && name) return pages[""]();
    await (pages[name] || pages[""])(arg, new URLSearchParams(qs || ""));
    scrollTo(0, 0);
  } catch (e) { main().innerHTML = `<h1>Something went wrong</h1><p class="err">${esc(e.message)}</p>`; }
}
addEventListener("hashchange", route);
route();
