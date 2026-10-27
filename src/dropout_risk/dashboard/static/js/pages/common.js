// Building blocks shared by the analytics dashboards.
import { get } from "../api.js";
import { heatmap, profileBars, shareBars } from "../charts.js";
import { card, empty, esc, grid, lift, pct, select, showError } from "../ui.js";

/** One share-bar card per question in a group. */
export async function breakdownGrid(root, group, params, { exclude = [], title } = {}) {
  if (title) root.appendChild(Object.assign(document.createElement("h2"), { textContent: title, className: "section-title" }));
  const g = grid(root);
  const data = await get("/breakdowns", { group, ...params() });
  for (const bd of data.filter((b) => !exclude.includes(b.feature))) {
    const { body } = card(g, { title: bd.title, sub: `Drop share by answer · ${bd.rows_total} rows · dashed line = average` });
    if (!bd.rows_total) empty(body); else shareBars(body, bd);
  }
  return data;
}

export async function profileCard(parent, feature, params, { title, sub } = {}) {
  const { body } = card(parent, { title: title || "", sub });
  try {
    const prof = await get(`/profile/${feature}`, params());
    body.closest(".card").querySelector("h2").textContent = title || prof.title;
    if (!prof.series.some((s) => s.n)) return empty(body);
    if (!sub && prof.description) body.closest(".card").querySelector(".card-head div").insertAdjacentHTML("beforeend", `<p class="sub">${esc(prof.description)} · share of each class</p>`);
    profileBars(body, prof);
  } catch (e) { showError(body, e); }
}

/** Heatmap card with selectable row / column questions. */
export function crosstabCard(parent, meta, params, { row, col, title = "Where risk concentrates", span = 2 }) {
  const options = meta.features.filter((f) => f.answers.length > 1).map((f) => ({ value: f.name, label: f.title }));
  const id = `ct-${Math.random().toString(36).slice(2, 7)}`;
  const actions = `<div class="toolbar">${select(`${id}-r`, "Rows", options, row)}${select(`${id}-c`, "Columns", options, col)}</div>`;
  const { card: c, body } = card(parent, { title, sub: "Drop share for every combination of two answers (n = respondents in the cell)", span, actions });
  const load = async () => {
    body.innerHTML = '<div class="skeleton"></div>';
    try {
      const ct = await get("/crosstab", { row: c.querySelector(`#${id}-r`).value, col: c.querySelector(`#${id}-c`).value, ...params() });
      if (!ct.row_labels.length) return empty(body);
      heatmap(body, ct);
    } catch (e) { showError(body, e); }
  };
  c.querySelectorAll("select").forEach((s) => s.addEventListener("change", load));
  return load();
}

/** Plain-language sentences for decision makers from risk-signal rows. */
export function insight(s, overall) {
  const dir = s.lift >= 1 ? "risk" : "protective";
  const verb = s.lift >= 1 ? `${lift(s.lift)} the average` : `${pct(1 - s.lift)} below the average`;
  return `<li class="${dir}">Students answering <b>“${esc(s.answer)}”</b> to <b>${esc(s.question)}</b> show a drop share of <b>${pct(s.drop_share)}</b> — ${verb} (${pct(overall)}), based on ${s.n} respondents.</li>`;
}
