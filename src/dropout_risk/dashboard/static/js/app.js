// Shell: navigation, global filter bar, theme, and hash routing (#/overview, #/segments, ...).
import { apiUrl, get } from "./api.js";
import { activeFilterCount, onChange, params, state, update } from "./state.js";
import { esc, select, showError } from "./ui.js";
import overview from "./pages/overview.js";
import segments from "./pages/segments.js";
import aiUsage from "./pages/ai-usage.js";
import learning from "./pages/learning.js";
import integrity from "./pages/integrity.js";
import drivers from "./pages/drivers.js";
import watchlist from "./pages/watchlist.js";
import simulator from "./pages/simulator.js";
import model from "./pages/model.js";
import quality from "./pages/quality.js";

const PAGES = [
  { section: "Executive", items: [overview, drivers] },
  { section: "Student analytics", items: [segments, aiUsage, learning, integrity] },
  { section: "Action", items: [watchlist, simulator] },
  { section: "Data & model", items: [model, quality] },
];
const ALL = PAGES.flatMap((s) => s.items);

const $ = (id) => document.getElementById(id);
let meta = null;

function applyTheme() {
  if (state.theme === "system") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", state.theme);
}

function renderNav(current) {
  $("nav").innerHTML = PAGES.map((s) => `<div class="section">${esc(s.section)}</div>` + s.items.map((p) =>
    `<a href="#/${p.id}" ${p.id === current ? 'aria-current="page"' : ""}>${esc(p.title)}</a>`).join("")).join("");
}

function renderToolbar(page) {
  const uses = page.filters || "none"; // "all" | "segments" | "none"
  const parts = [];
  if (uses === "all") {
    parts.push(select("f-source", "Data source", meta.sources.map((s) => ({ value: s.id, label: `${s.label} · ${s.rows}` })), state.source));
  }
  if (uses !== "none") {
    for (const name of meta.segment_filters) {
      const f = meta.features.find((x) => x.name === name);
      parts.push(select(`f-${name}`, f.title, [{ value: "", label: "All" }, ...f.answers.map((a) => ({ value: a.code, label: a.label }))],
        state.filters[name] ?? ""));
    }
    if (activeFilterCount()) parts.push(`<button class="btn" id="f-reset" type="button">Reset filters</button>`);
  }
  if (uses === "all") {
    parts.push(`<a class="btn" id="f-export" href="${apiUrl("/dataset", { ...params(), format: "csv" })}" title="Download the rows behind this view">Export CSV</a>`);
  }
  $("toolbar").innerHTML = parts.join("");
  $("f-source")?.addEventListener("change", (e) => update({ source: e.target.value }));
  for (const name of meta.segment_filters) {
    $(`f-${name}`)?.addEventListener("change", (e) => update({ filters: { ...state.filters, [name]: e.target.value } }));
  }
  $("f-reset")?.addEventListener("click", () => update({ filters: {} }));

  const note = $("filter-note");
  const msgs = [];
  if (uses === "all" && state.source !== "original") {
    msgs.push("You are viewing SMOTE-augmented data: classes are balanced to 50 / 50 by design, so read drop shares as <b>relative</b> (compare answers against the average line), not as real-world rates. Switch the data source to <b>Original survey</b> for observed rates.");
  }
  if (page.note) msgs.push(page.note);
  note.innerHTML = msgs.join("<br>");
  note.hidden = msgs.length === 0;
}

async function route() {
  const id = (location.hash.match(/^#\/([\w-]+)/) || [])[1] || "overview";
  const page = ALL.find((p) => p.id === id) || overview;
  renderNav(page.id);
  $("page-title").textContent = page.title;
  $("page-subtitle").textContent = page.subtitle || "";
  renderToolbar(page);
  const root = $("page");
  root.innerHTML = "";
  try {
    await page.render(root, { meta, params, state });
  } catch (err) {
    console.error(err);
    showError(root, err);
  }
}

async function start() {
  applyTheme();
  $("theme").value = state.theme;
  $("theme").addEventListener("change", (e) => { update({ theme: e.target.value }); applyTheme(); route(); });
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => state.theme === "system" && route());
  try {
    meta = await get("/meta");
  } catch (err) {
    showError($("page"), err);
    return;
  }
  if (!meta.sources.some((s) => s.id === state.source)) state.source = meta.default_source;
  onChange(() => route());
  window.addEventListener("hashchange", route);
  route();
}

start();
