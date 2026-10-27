// Student Dropout Risk UI: risk-check form (POST /api/predict) and dashboards (GET /api/dashboard).
const SCHEMA = JSON.parse(document.getElementById("form-schema").textContent);
const C = { accent: "#DBCC23", ink: "#20211D", page: "#F7F6F0", surface: "#FFFFFF", muted: "#74756C",
  grid: "rgba(32,33,29,0.08)", axis: "rgba(32,33,29,0.22)" };
const FONT = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';

const $ = (sel, root = document) => root.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = (x, d = 0) => (x == null ? "–" : `${(x * 100).toFixed(d)}%`);
const probText = (p) => (p >= 0.999 ? ">99.9%" : p <= 0.001 ? "<0.1%" : pct(p, 1));
const cap = (s) => s[0].toUpperCase() + s.slice(1);

// ---------------------------------------------------------------------------------------------
// Routing
const views = { check: $("#view-check"), dashboards: $("#view-dashboards") };
let dashboardLoaded = false;
function route() {
  const [, first, second] = location.hash.match(/^#\/(\w+)(?:\/([\w-]+))?/) || [];
  const view = first === "dashboards" ? "dashboards" : "check";
  if (view === "dashboards" && second && TABS.some((t) => t.id === second) && second !== activeTab) {
    activeTab = second;
    if (D) { renderTabBar(); renderActiveTab(); }
  }
  Object.entries(views).forEach(([k, el]) => { el.hidden = k !== view; });
  document.querySelectorAll(".tabs a").forEach((a) =>
    (a.dataset.view === view ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
  if (view === "dashboards" && !dashboardLoaded) { dashboardLoaded = true; loadDashboard(); }
  if (view === "dashboards") window.dispatchEvent(new Event("resize")); // let hidden charts re-measure
}
window.addEventListener("hashchange", route);

// ---------------------------------------------------------------------------------------------
// Risk check form
const EXAMPLES = {
  risk: { gender: "Male", major: "Engineering & Tech", degree: "Bachelor", study_year: "2nd year", residence: "Capital",
    university_type: "Public", ever_used_ai: "Yes", ai_study_frequency: "Always", ai_replaces_research: "Always",
    analytical_skills_effect: "Negative", independent_learning: "No", motivation_effect: "Reduces", over_reliance: "Yes",
    ai_cheating_view: "No", submitted_full_project: "Yes", reviews_content: "Never", content_errors: "Often",
    used_ai_in_exam: "Yes", saves_time: "Greatly", flagged_by_professor: "Yes", professor_was_right: "Partly",
    detector_knowledge: "Weak", easy_to_detect: "Sometimes", ai_improved_education: "Somewhat",
    ai_replaces_search_engines: "Always", ai_tools: ["ChatGPT"], learned_prompting: "No", advice: "" },
  safe: { gender: "Female", major: "Medical", degree: "Bachelor", study_year: "4th year", residence: "Capital",
    university_type: "Public", ever_used_ai: "Yes", ai_study_frequency: "Sometimes", ai_replaces_research: "Rarely",
    analytical_skills_effect: "Positive", independent_learning: "Yes", motivation_effect: "Increases", over_reliance: "No",
    ai_cheating_view: "Depends on use", submitted_full_project: "No", reviews_content: "Always", content_errors: "Sometimes",
    used_ai_in_exam: "No", saves_time: "Greatly", flagged_by_professor: "No", professor_was_right: "Never flagged",
    detector_knowledge: "Good", easy_to_detect: "Yes", ai_improved_education: "Yes",
    ai_replaces_search_engines: "Sometimes", ai_tools: ["ChatGPT", "Google Gemini"], learned_prompting: "Yes",
    advice: "Use it to understand concepts and always verify the sources." },
};

const form = $("#student-form");
const required = SCHEMA.questions.filter((q) => q.type === "choice" && !q.optional);
$("#required").textContent = required.length;

function renderForm() {
  $("#form-groups").innerHTML = SCHEMA.groups.map((group) => {
    const qs = SCHEMA.questions.filter((q) => q.group === group);
    return `<section class="card group"><h2>${esc(group)}</h2>${qs.map(question).join("")}</section>`;
  }).join("");
}

function question(q) {
  const opt = q.optional ? '<span class="opt">optional</span>' : "";
  if (q.type === "text") {
    return `<div class="question" data-field="${q.field}"><label class="q-title" for="q-${q.field}">${esc(q.title)} ${opt}</label>
      <textarea id="q-${q.field}" name="${q.field}" placeholder="Type the student's answer, or leave empty"></textarea></div>`;
  }
  const type = q.type === "multi" ? "checkbox" : "radio";
  return `<div class="question" data-field="${q.field}" role="${type === "radio" ? "radiogroup" : "group"}" aria-labelledby="t-${q.field}">
    <div class="q-title" id="t-${q.field}">${esc(q.title)} ${q.type === "multi" ? '<span class="opt">select all that apply</span>' : opt}</div>
    <div class="pills">${q.options.map((o) => `<label class="pill"><input type="${type}" name="${q.field}" value="${esc(o)}"><span>${esc(o)}</span></label>`).join("")}</div>
  </div>`;
}

function readForm() {
  const data = new FormData(form);
  const out = {};
  for (const q of SCHEMA.questions) {
    if (q.type === "multi") out[q.field] = data.getAll(q.field);
    else if (q.type === "text") out[q.field] = (data.get(q.field) || "").trim();
    else out[q.field] = data.get(q.field) ?? (q.optional ? "" : null);
  }
  if (out.learned_prompting === "Not sure") out.learned_prompting = "";
  return out;
}

function fillForm(values) {
  form.reset();
  for (const [field, value] of Object.entries(values)) {
    const vals = Array.isArray(value) ? value : [value];
    form.querySelectorAll(`[name="${field}"]`).forEach((input) => {
      if (input.tagName === "TEXTAREA") input.value = value;
      else input.checked = vals.includes(input.value);
    });
  }
  updateProgress();
}

function updateProgress() {
  const values = readForm();
  const done = required.filter((q) => values[q.field]).length;
  $("#answered").textContent = done;
  $("#progress-fill").style.width = `${(done / required.length) * 100}%`;
  required.forEach((q) => { if (values[q.field]) form.querySelector(`[data-field="${q.field}"]`).classList.remove("missing"); });
}

let lastPayload = null;
async function submit(evt) {
  evt?.preventDefault();
  const values = readForm();
  const missing = required.filter((q) => !values[q.field]);
  const err = $("#form-error");
  missing.forEach((q) => form.querySelector(`[data-field="${q.field}"]`).classList.add("missing"));
  if (missing.length) {
    err.textContent = `Please answer ${missing.length} more question${missing.length > 1 ? "s" : ""} (marked Required).`;
    err.hidden = false;
    form.querySelector(`[data-field="${missing[0].field}"]`).scrollIntoView({ behavior: "smooth", block: "center" });
    return;
  }
  err.hidden = true;
  const btn = $("#submit");
  btn.disabled = true; btn.textContent = "Assessing…";
  try {
    const res = await fetch("/api/predict", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(values) });
    const body = await res.json();
    if (!res.ok) throw new Error(Array.isArray(body.detail) ? body.detail.map((d) => `${d.field || d.loc?.join(".")}: ${d.message || d.msg}`).join("; ") : body.detail);
    lastPayload = values;
    renderResult(body);
    if (window.innerWidth <= 980) $("#result").scrollIntoView({ behavior: "smooth" });
  } catch (e) {
    err.textContent = `Could not assess risk: ${e.message}`;
    err.hidden = false;
  } finally {
    btn.disabled = false; btn.textContent = "Assess dropout risk";
  }
}

function renderResult(r) {
  const maxImpact = Math.max(...[...r.factors_increasing_risk, ...r.factors_decreasing_risk].map((f) => Math.abs(f.impact)), 1e-9);
  const factor = (f, dir) => `<div class="factor"><span class="text">${esc(f.factor)}</span>
    <div class="bar ${dir}"><i style="width:${(Math.abs(f.impact) / maxImpact) * 100}%"></i></div>
    <span class="none" style="text-align:right">${f.impact > 0 ? "+" : ""}${f.impact.toFixed(2)}</span></div>`;
  const bands = { medium: 0.3, high: 0.6 };
  $("#result").innerHTML = `
    <div class="verdict">
      <div><div class="label">Dropout probability</div><div class="prob">${probText(r.drop_probability)}</div>
        <div class="pred">Prediction: ${esc(r.prediction)}</div></div>
      <span class="chip ${r.risk_level}">${cap(r.risk_level)} risk</span>
    </div>
    <div class="gauge" role="img" aria-label="Dropout probability ${pct(r.drop_probability)}">
      <div class="gauge-fill" style="width:${r.drop_probability * 100}%"></div>
      <div class="gauge-tick" style="left:${bands.medium * 100}%"></div><div class="gauge-tick" style="left:${bands.high * 100}%"></div>
    </div>
    <div class="gauge-scale"><span style="left:0">0%</span><span style="left:${bands.medium * 100}%">Medium</span><span style="left:${bands.high * 100}%">High</span><span style="left:100%">100%</span></div>
    <div class="factors">
      <h3>Raising risk</h3>${r.factors_increasing_risk.map((f) => factor(f, "up")).join("") || '<p class="none">No factors raise this student\'s risk.</p>'}
      <h3>Lowering risk</h3>${r.factors_decreasing_risk.map((f) => factor(f, "down")).join("") || '<p class="none">No factors lower this student\'s risk.</p>'}
    </div>
    <p class="none" style="margin-top:12px">Impact = contribution to the model's log-odds of dropping out. Model: ${esc(r.model)}.</p>
    <details><summary>Processed input sent to the model</summary><pre>${esc(JSON.stringify(r.processed_input, null, 2))}</pre></details>`;
}

renderForm();
form.addEventListener("change", () => { updateProgress(); if (lastPayload) submit(); });
form.addEventListener("submit", submit);
document.querySelectorAll("[data-example]").forEach((b) => b.addEventListener("click", () => { fillForm(EXAMPLES[b.dataset.example]); submit(); }));
$("#clear-form").addEventListener("click", () => {
  form.reset(); lastPayload = null; updateProgress();
  form.querySelectorAll(".missing").forEach((el) => el.classList.remove("missing"));
  $("#form-error").hidden = true;
});
updateProgress();

// ---------------------------------------------------------------------------------------------
// Dashboards
const CONFIG = { displayModeBar: false, responsive: true };
const filters = { major: "", study_year: "", gender: "", university_type: "" };
const FILTER_LABELS = { major: "Major", study_year: "Study year", gender: "Gender", university_type: "University type" };
let activeSection = null;

function layout(extra = {}) {
  const axis = { gridcolor: C.grid, zerolinecolor: C.axis, linecolor: C.axis, tickfont: { color: C.muted, size: 11 },
    title: { font: { color: C.muted, size: 12 } }, automargin: true, fixedrange: true };
  return {
    paper_bgcolor: C.surface, plot_bgcolor: C.surface, font: { family: FONT, size: 12, color: C.ink },
    margin: { l: 8, r: 40, t: 10, b: 30 }, showlegend: false, bargap: 0.35, barcornerradius: 4,
    hoverlabel: { bgcolor: C.ink, bordercolor: C.ink, font: { color: C.surface, family: FONT } },
    legend: { orientation: "h", x: 0, y: 1.14, font: { color: C.ink } },
    ...extra, xaxis: { ...axis, ...(extra.xaxis || {}) }, yaxis: { ...axis, ...(extra.yaxis || {}) },
  };
}
// Charts are drawn while their grid is still filling up, so a card's width changes after the first
// draw. Observing each chart keeps it sized to its card.
// Only the width follows the card; each chart keeps the height it was drawn with.
const resizer = new ResizeObserver((entries) => entries.forEach(({ target: el }) => {
  const w = Math.floor(el.clientWidth);
  if (el.isConnected && el._fullLayout && w > 0 && Math.abs(el._fullLayout.width - w) > 1) Plotly.relayout(el, { width: w });
}));
const draw = (el, data, lay) => { Plotly.react(el, data, lay, CONFIG); resizer.observe(el); };
const wrap = (s, n = 42) => {
  const out = [""];
  for (const w of String(s).split(" ")) { if ((out.at(-1) + " " + w).trim().length > n) out.push(w); else out[out.length - 1] = (out.at(-1) + " " + w).trim(); }
  return out.join("<br>");
};

function card(parent, { title, sub = "", span = false }) {
  const el = document.createElement("article");
  el.className = `card${span ? " span-2" : ""}`;
  el.innerHTML = `<h2>${esc(title)}</h2>${sub ? `<p class="sub">${sub}</p>` : ""}<div class="chart"></div>`;
  parent.appendChild(el);
  return el.querySelector(".chart");
}
function grid(parent, cls = "") {
  const g = document.createElement("section");
  g.className = `grid ${cls}`;
  parent.appendChild(g);
  return g;
}

/** Drop share per answer. Answers above the average are highlighted in the accent color. */
function shareBars(el, bd) {
  const rows = bd.answers.filter((a) => a.n > 0);
  const avg = bd.overall_drop_share;
  draw(el, [{
    type: "bar", orientation: "h", y: rows.map((a) => a.label), x: rows.map((a) => a.drop_share),
    marker: { color: rows.map((a) => (a.drop_share > avg ? C.accent : C.muted)) },
    text: rows.map((a) => pct(a.drop_share)), textposition: "outside", cliponaxis: false, textfont: { size: 11, color: C.ink },
    customdata: rows.map((a) => [a.n, a.drop, a.lift ?? 0]),
    hovertemplate: "<b>%{y}</b><br>Drop share %{x:.0%}<br>%{customdata[0]} students · %{customdata[1]} dropped<br>%{customdata[2]:.2f}× the average<extra></extra>",
  }], layout({
    height: 50 + rows.length * 30, margin: { l: 8, r: 44, t: 18, b: 26 },
    xaxis: { tickformat: ".0%", range: [0, 1.08] }, yaxis: { autorange: "reversed", gridcolor: "rgba(0,0,0,0)" },
    shapes: [{ type: "line", x0: avg, x1: avg, yref: "paper", y0: 0, y1: 1, line: { color: C.ink, width: 1, dash: "dot" } }],
    annotations: [{ x: avg, yref: "paper", y: 1, yanchor: "bottom", text: `average ${pct(avg)}`, showarrow: false, font: { size: 10, color: C.muted } }],
  }));
}

/** Lift bars around 1×: accent = raises risk, muted = lowers risk. */
function liftBars(el, signals) {
  const lifts = signals.map((s) => s.lift);
  const lo = Math.min(1, ...lifts), hi = Math.max(1, ...lifts), pad = Math.max(0.12, (hi - lo) * 0.22);
  draw(el, [{
    type: "bar", orientation: "h", y: signals.map((s) => wrap(`${s.question}: ${s.answer}`)), x: signals.map((s) => s.lift - 1), base: 1,
    marker: { color: signals.map((s) => (s.lift >= 1 ? C.accent : C.muted)) },
    // protective bars run left towards the question labels, so their value sits inside the bar
    text: signals.map((s) => `${s.lift.toFixed(2)}×`), textposition: lifts.map((l) => (l < 1 ? "inside" : "outside")),
    insidetextanchor: "start", cliponaxis: false,
    textfont: { size: 11, color: lifts.map((l) => (l < 1 ? C.surface : C.ink)) },
    customdata: signals.map((s) => [s.drop_share, s.n]),
    hovertemplate: "<b>%{y}</b><br>%{text} the average drop share<br>Drop share %{customdata[0]:.0%} of %{customdata[1]} students<extra></extra>",
  }], layout({
    height: 30 + signals.length * 40, margin: { l: 8, r: 48, t: 6, b: 34 },
    xaxis: { ticksuffix: "×", zeroline: false, range: [Math.max(0, lo - pad), hi + pad], title: { text: "Compared with the average (1× = average)" } },
    yaxis: { autorange: "reversed", gridcolor: "rgba(0,0,0,0)", tickfont: { size: 11, color: C.ink } },
    shapes: [{ type: "line", x0: 1, x1: 1, yref: "paper", y0: 0, y1: 1, line: { color: C.ink, width: 1 } }],
  }));
}

function classBars(el, categories, noDrop, drop, { percent = true, height = 260 } = {}) {
  const series = [["No drop", noDrop, C.muted], ["Drop", drop, C.accent]];
  draw(el, series.map(([name, values, color]) => ({
    type: "bar", name, x: categories, y: values, marker: { color, line: { color: C.surface, width: 2 } },
    text: values.map((v) => (percent ? pct(v) : v)), textposition: "outside", cliponaxis: false, textfont: { size: 10, color: C.ink },
    hovertemplate: `<b>${name}</b><br>%{x}: %{y${percent ? ":.0%" : ""}}<extra></extra>`,
  })), layout({ height, showlegend: true, bargroupgap: 0.06, margin: { l: 8, r: 10, t: 36, b: 30 },
    yaxis: { tickformat: percent ? ".0%" : "", rangemode: "tozero" }, xaxis: { type: "category", gridcolor: "rgba(0,0,0,0)" } }));
}

function heatmap(el, ct) {
  draw(el, [{
    type: "heatmap", z: ct.drop_share, x: ct.col_labels, y: ct.row_labels, zmin: 0, zmax: 1, xgap: 3, ygap: 3,
    colorscale: [[0, C.page], [0.5, C.accent], [1, C.ink]],
    text: ct.drop_share.map((r, i) => r.map((v, j) => (v == null ? "" : `${pct(v)}<br>n=${ct.n[i][j]}`))), texttemplate: "%{text}", textfont: { size: 11 },
    customdata: ct.n, hoverongaps: false,
    hovertemplate: `<b>%{y} · %{x}</b><br>Drop share %{z:.0%} (%{customdata} students)<extra></extra>`,
    colorbar: { title: { text: "Drop share", side: "right", font: { color: C.muted, size: 11 } }, tickformat: ".0%", thickness: 10, outlinewidth: 0, tickfont: { color: C.muted, size: 10 } },
  }], layout({ height: 90 + ct.row_labels.length * 50, margin: { l: 8, r: 8, t: 8, b: 40 },
    xaxis: { title: { text: ct.col_title }, type: "category", gridcolor: "rgba(0,0,0,0)" },
    yaxis: { title: { text: ct.row_title }, type: "category", autorange: "reversed", gridcolor: "rgba(0,0,0,0)" } }));
}

function kpi(parent, label, value, note = "", accent = false) {
  parent.insertAdjacentHTML("beforeend", `<article class="card kpi${accent ? " accent" : ""}"><div class="k-label">${esc(label)}</div>
    <div class="k-value">${value}</div>${note ? `<div class="k-note">${note}</div>` : ""}</article>`);
}

function renderFilters(options) {
  const box = $("#filters");
  box.innerHTML = Object.entries(FILTER_LABELS).map(([key, label]) => `<label class="field" for="flt-${key}">${label}
    <select id="flt-${key}" data-key="${key}"><option value="">All</option>${options[key].map((o) =>
      `<option value="${o.code}" ${String(filters[key]) === String(o.code) ? "selected" : ""}>${esc(o.label)}</option>`).join("")}</select></label>`).join("")
    + `<button class="btn ghost" type="button" id="flt-reset" ${Object.values(filters).some((v) => v !== "") ? "" : "hidden"}>Reset filters</button>`;
  box.querySelectorAll("select").forEach((s) => s.addEventListener("change", () => { filters[s.dataset.key] = s.value; loadDashboard(); }));
  $("#flt-reset").addEventListener("click", () => { Object.keys(filters).forEach((k) => { filters[k] = ""; }); loadDashboard(); });
}

// Scorecard: key indicators (rows) for each group of one question (columns).
function scorecard(el, sc) {
  if (sc.hidden_groups.length) {
    el.insertAdjacentHTML("beforebegin", `<p class="sub">Not shown (fewer than ${sc.min_n} students): ${sc.hidden_groups.map((g) => `${esc(g.label)} (n=${g.n})`).join(", ")}</p>`);
  }
  if (!sc.groups.length) return empty(el, "No group has enough students.");
  const z = sc.metrics.map((m) => m.values);
  draw(el, [{
    type: "heatmap", z, x: sc.groups.map((g) => `${g.label}<br><span style="font-size:10px">n=${g.n}</span>`), y: sc.metrics.map((m) => m.label),
    zmin: 0, zmax: 1, xgap: 3, ygap: 3, colorscale: [[0, C.page], [0.5, C.accent], [1, C.ink]], showscale: false,
    text: z.map((r) => r.map((v) => pct(v))), texttemplate: "%{text}", textfont: { size: 11 },
    hovertemplate: "<b>%{y}</b><br>%{x}: %{z:.0%}<extra></extra>",
  }], layout({ height: 70 + sc.metrics.length * 30, margin: { l: 8, r: 8, t: 8, b: 44 },
    xaxis: { type: "category", side: "bottom", gridcolor: "rgba(0,0,0,0)", tickfont: { size: 11, color: C.ink } },
    yaxis: { type: "category", autorange: "reversed", gridcolor: "rgba(0,0,0,0)", tickfont: { size: 11, color: C.ink } } }));
}

const LEGEND_ABOVE = `<span class="legend"><span><i style="background:${C.accent}"></i>above average</span><span><i style="background:${C.muted}"></i>at or below</span></span>`;
const SCORE_SUB = "Share of students in each group · darker = higher";
const empty = (el, text = "Not enough data.") => { el.innerHTML = `<p class="sub">${esc(text)}</p>`; };

// ---- dashboard tabs --------------------------------------------------------------------------
const TABS = [
  { id: "overview", title: "Overview", render: renderOverview },
  { id: "jordan", title: "Jordan & universities", render: renderJordan },
  { id: "groups", title: "Student groups", render: renderGroups },
  { id: "differ", title: "How dropouts differ", render: renderDiffer },
  { id: "topics", title: "Explore by topic", render: renderTopics },
];
let activeTab = "overview";
let D = null;

function renderOverview(root, d) {
  const s = d.summary;
  const tiles = grid(root, "kpis");
  kpi(tiles, "Students", s.students.toLocaleString(), Object.keys(d.filters.applied).length ? "matching the filters" : "in the dataset");
  kpi(tiles, "Dropout rate", pct(s.drop_share, 1), `${s.drop_count.toLocaleString()} students dropped`, true);
  kpi(tiles, "Retained", s.no_drop_count.toLocaleString(), `${pct(1 - s.drop_share, 1)} of students`);
  if (d.model) kpi(tiles, "Prediction accuracy", pct(d.model.test.accuracy, 1), `${d.model.name} · catches ${pct(d.model.test.recall)} of dropouts`);

  const sig = grid(root);
  const risk = d.key_signals.risk, prot = d.key_signals.protective;
  const r1 = card(sig, { title: "Strongest warning signs", sub: "Answers linked to the highest dropout rates (minimum group size applies)" });
  risk.length ? liftBars(r1, risk) : empty(r1);
  const r2 = card(sig, { title: "Strongest protective answers", sub: "Answers linked to the lowest dropout rates" });
  prot.length ? liftBars(r2, prot) : empty(r2);

  const g = grid(root);
  shareBars(card(g, { title: "Dropout rate by university type", sub: `Public vs private · ${LEGEND_ABOVE}` }), d.jordan.university_type.breakdown);
  shareBars(card(g, { title: "Dropout rate by residence", sub: `Capital vs the governorates · ${LEGEND_ABOVE}` }), d.jordan.residence.breakdown);
  heatmap(card(grid(root), { title: "Dropout hot-spots: major × study year", sub: "Dropout rate in each group (n = students)", span: true }), d.heatmap);
}

function renderJordan(root, d) {
  const j = d.jordan;
  // headline tiles: students and dropout rate per group, summed from the answer breakdowns
  const group = (bd, labels) => {
    const rows = bd.answers.filter((a) => labels.includes(a.label));
    const n = rows.reduce((s, a) => s + a.n, 0), drop = rows.reduce((s, a) => s + a.drop, 0);
    return { n, rate: n ? drop / n : null, share: bd.rows_total ? n / bd.rows_total : null };
  };
  const tile = (parent, label, g, accent) => kpi(parent, label, g.n.toLocaleString(),
    `${pct(g.share)} of students · dropout rate ${pct(g.rate, 1)}`, accent);
  const uni = j.university_type.breakdown, res = j.residence.breakdown;
  const tiles = grid(root, "kpis");
  tile(tiles, "Public university students", group(uni, ["Public"]), true);
  tile(tiles, "Private university students", group(uni, ["Private"]));
  tile(tiles, "Living in the capital", group(res, ["Capital"]));
  tile(tiles, "Living outside the capital", group(res, ["Governorate", "District (liwa)", "Village"]));

  root.insertAdjacentHTML("beforeend", '<h2 class="section-title">Public vs private universities</h2>');
  const u = grid(root);
  shareBars(card(u, { title: "Dropout rate by university type", sub: LEGEND_ABOVE }), j.university_type.breakdown);
  scorecard(card(u, { title: "University type scorecard", sub: SCORE_SUB }), j.university_type.scorecard);

  root.insertAdjacentHTML("beforeend", '<h2 class="section-title">Capital and the governorates</h2>');
  const r = grid(root);
  shareBars(card(r, { title: "Dropout rate by residence", sub: LEGEND_ABOVE }), j.residence.breakdown);
  scorecard(card(r, { title: "Residence scorecard", sub: SCORE_SUB }), j.residence.scorecard);

  root.insertAdjacentHTML("beforeend", '<h2 class="section-title">Where university type and place meet</h2>');
  const h = grid(root);
  for (const ct of j.heatmaps) {
    heatmap(card(h, { title: `${ct.row_title} × ${ct.col_title}`, sub: "Dropout rate in each group (n = students)" }), ct);
  }
}

function renderGroups(root, d) {
  for (const sc of Object.values(d.groups)) {
    root.insertAdjacentHTML("beforeend", `<h2 class="section-title">By ${esc(sc.title.toLowerCase())}</h2>`);
    const g = grid(root);
    const bd = d.sections.flatMap((s) => s.charts).find((c) => c.feature === sc.feature);
    if (bd) shareBars(card(g, { title: `Dropout rate by ${sc.title.toLowerCase()}`, sub: LEGEND_ABOVE }), bd);
    scorecard(card(g, { title: `${sc.title} scorecard`, sub: SCORE_SUB }), sc);
  }
}

function renderDiffer(root, d) {
  const prof = grid(root);
  for (const p of d.profiles) {
    classBars(card(prof, { title: p.title, sub: `${esc(p.description)} · share of each group` }), p.labels, p.series[0].shares, p.series[1].shares);
  }
  const t = d.tools;
  classBars(card(prof, { title: "AI tool adoption", sub: "Share of each group using the tool" }), t.map((x) => x.title),
    t.map((x) => x.adoption["No drop"]), t.map((x) => x.adoption["Drop"]));
}

function renderTopics(root, d) {
  root.insertAdjacentHTML("beforeend", '<div class="section-tabs" id="topic-tabs"></div><section class="grid" id="topic-body"></section>');
  if (!d.sections.some((x) => x.id === activeSection)) activeSection = d.sections[0].id;
  const tabs = $("#topic-tabs");
  tabs.innerHTML = d.sections.map((x) => `<button type="button" data-id="${x.id}" aria-pressed="${x.id === activeSection}">${esc(x.title)}</button>`).join("");
  const show = () => {
    const body = $("#topic-body");
    body.innerHTML = "";
    for (const bd of d.sections.find((x) => x.id === activeSection).charts) {
      shareBars(card(body, { title: bd.title, sub: `Dropout rate by answer · ${LEGEND_ABOVE}` }), bd);
    }
  };
  tabs.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
    activeSection = b.dataset.id;
    tabs.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    show();
  }));
  show();
}

function renderTabBar() {
  const bar = $("#dash-tabs");
  bar.innerHTML = TABS.map((t) => `<button type="button" role="tab" data-id="${t.id}" aria-selected="${t.id === activeTab}">${esc(t.title)}</button>`).join("");
  bar.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => { location.hash = `#/dashboards/${b.dataset.id}`; }));
}

function renderActiveTab() {
  const root = $("#dashboard");
  root.innerHTML = "";
  if (!D.summary.students) {
    root.innerHTML = '<div class="error-box">No students match these filters.</div>';
    return;
  }
  TABS.find((t) => t.id === activeTab).render(root, D);
}

async function loadDashboard() {
  const root = $("#dashboard");
  root.innerHTML = '<div class="grid kpis"><div class="card skeleton"></div><div class="card skeleton"></div><div class="card skeleton"></div><div class="card skeleton"></div></div>';
  const qs = new URLSearchParams(Object.entries(filters).filter(([, v]) => v !== ""));
  try {
    const res = await fetch(`/api/dashboard?${qs}`);
    const body = await res.json();
    if (!res.ok) throw new Error(body.detail);
    D = body;
  } catch (e) {
    root.innerHTML = `<div class="error-box">Could not load dashboards: ${esc(e.message)}</div>`;
    return;
  }
  renderFilters(D.filters.options);
  renderTabBar();
  renderActiveTab();
}

route();
