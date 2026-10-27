// Small DOM helpers shared by the dashboards.
export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export const pct = (x, digits = 0) => (x == null ? "–" : `${(x * 100).toFixed(digits)}%`);
export const num = (x, digits = 0) => (x == null ? "–" : Number(x).toLocaleString(undefined,
  { minimumFractionDigits: digits, maximumFractionDigits: digits }));
export const lift = (x) => (x == null ? "–" : `${x.toFixed(2)}×`);

export function el(html) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

export function grid(parent, cls = "") {
  return parent.appendChild(el(`<section class="grid ${cls}"></section>`));
}

/** A chart/table card. Returns { card, body } where body is the content container. */
export function card(parent, { title, sub = "", span = 1, chart = true, actions = "" }) {
  const c = parent.appendChild(el(`
    <article class="card ${span === 2 ? "span-2" : ""}">
      <div class="card-head"><div><h2>${esc(title)}</h2>${sub ? `<p class="sub">${esc(sub)}</p>` : ""}</div>${actions}</div>
      <div class="${chart ? "chart" : "content"}"><div class="skeleton"></div></div>
    </article>`));
  return { card: c, body: c.querySelector(chart ? ".chart" : ".content") };
}

export function kpi(parent, { label, value, note = "" }) {
  parent.appendChild(el(`
    <article class="card kpi">
      <div class="label">${esc(label)}</div>
      <div class="value">${value}</div>
      ${note ? `<div class="note">${note}</div>` : ""}
    </article>`));
}

export const chip = (band) => `<span class="chip ${esc(band)}">${esc(band[0].toUpperCase() + band.slice(1))} risk</span>`;

export function barCell(value, max, color, label) {
  const w = max ? Math.max(0, Math.min(100, (value / max) * 100)) : 0;
  return `<div class="bar-cell"><div class="track"><div class="fill" style="width:${w}%;background:${color}"></div></div><span>${label}</span></div>`;
}

/** columns: [{key, label, num?, render?(row)}] */
export function table(columns, rows, { rowClass } = {}) {
  const head = columns.map((c) => `<th class="${c.num ? "num" : ""}">${esc(c.label)}</th>`).join("");
  const body = rows.map((r) => `<tr class="${rowClass ? rowClass(r) : ""}">${columns.map((c) =>
    `<td class="${c.num ? "num" : ""}">${c.render ? c.render(r) : esc(r[c.key])}</td>`).join("")}</tr>`).join("");
  return `<div class="table-wrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

export function showError(container, err) {
  const msg = err?.status === 503
    ? `${esc(err.message)}`
    : `Could not load data: ${esc(err?.message || err)}`;
  container.innerHTML = `<div class="error">${msg}</div>`;
}

export function empty(container, text = "No respondents match the current filters.") {
  container.innerHTML = `<div class="empty">${esc(text)}</div>`;
}

export function select(id, label, options, value) {
  return `<label class="field" for="${id}">${esc(label)}<select id="${id}">${options.map((o) =>
    `<option value="${esc(o.value)}" ${String(o.value) === String(value) ? "selected" : ""}>${esc(o.label)}</option>`).join("")}</select></label>`;
}
