// Plotly chart helpers. Colors come from CSS tokens so light/dark mode stay in sync; every chart
// has a hover layer, thin marks, a recessive grid and text in ink (not series) colors.
import { esc, pct } from "./ui.js";

const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

export function theme() {
  return {
    surface: css("--surface"), ink: css("--ink"), ink2: css("--ink-2"), muted: css("--muted"),
    grid: css("--grid"), axis: css("--axis"), noDrop: css("--c-nodrop"), drop: css("--c-drop"),
    real: css("--c-real"), synthetic: css("--c-synthetic"), risk: css("--c-risk"),
    protective: css("--c-protective"), neutral: css("--c-neutral"),
    seq: [0, 1, 2, 3, 4].map((i) => css(`--seq-${i}`)),
  };
}

const CONFIG = { displayModeBar: false, responsive: true };
const FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif';
const wrap = (s, n = 34) => {
  const words = String(s).split(" "); const lines = [""];
  for (const w of words) {
    if ((lines.at(-1) + " " + w).trim().length > n) lines.push(w); else lines[lines.length - 1] = (lines.at(-1) + " " + w).trim();
  }
  return lines.join("<br>");
};

function layout(t, extra = {}) {
  const axis = { gridcolor: t.grid, zerolinecolor: t.axis, linecolor: t.axis, tickfont: { color: t.muted, size: 11 },
    title: { font: { color: t.ink2, size: 12 } }, automargin: true, fixedrange: true };
  return {
    paper_bgcolor: t.surface, plot_bgcolor: t.surface,
    font: { family: FONT, size: 12, color: t.ink2 },
    margin: { l: 8, r: 18, t: 8, b: 30 },
    hoverlabel: { bgcolor: t.surface, bordercolor: t.axis, font: { color: t.ink, family: FONT } },
    showlegend: false, bargap: 0.35, barcornerradius: 4,
    legend: { orientation: "h", x: 0, y: 1.12, font: { color: t.ink2 } },
    ...extra,
    xaxis: { ...axis, ...(extra.xaxis || {}) },
    yaxis: { ...axis, ...(extra.yaxis || {}) },
  };
}

// Cards are added to auto-fit grids one by one, so a chart's width changes after its first draw.
// Only the width follows the card; each chart keeps the height it was drawn with.
const resizer = new ResizeObserver((entries) => entries.forEach(({ target: el }) => {
  const w = Math.floor(el.clientWidth);
  if (el.isConnected && el._fullLayout && w > 0 && Math.abs(el._fullLayout.width - w) > 1) Plotly.relayout(el, { width: w });
}));

export function draw(el, data, lay) { Plotly.react(el, data, lay, CONFIG); resizer.observe(el); }

/** Horizontal bars: drop share per answer, dashed line at the overall share. */
export function shareBars(el, bd) {
  const t = theme();
  const rows = bd.answers.filter((a) => a.n > 0);
  draw(el, [{
    type: "bar", orientation: "h", y: rows.map((a) => a.label), x: rows.map((a) => a.drop_share),
    marker: { color: t.drop }, text: rows.map((a) => pct(a.drop_share)), textposition: "outside",
    textfont: { color: t.ink2, size: 11 }, cliponaxis: false,
    customdata: rows.map((a) => [a.n, a.drop, a.lift ?? 0, a.pct_of_rows]),
    hovertemplate: "<b>%{y}</b><br>Drop share %{x:.0%}<br>%{customdata[0]} respondents (%{customdata[1]} drop, %{customdata[3]:.0%} of rows)<br>Lift %{customdata[2]:.2f}×<extra></extra>",
  }], layout(t, {
    height: 56 + rows.length * 30,
    margin: { l: 8, r: 40, t: 18, b: 26 },
    xaxis: { tickformat: ".0%", range: [0, 1.05] },
    yaxis: { autorange: "reversed", gridcolor: "rgba(0,0,0,0)" },
    shapes: bd.overall_drop_share == null ? [] : [{ type: "line", x0: bd.overall_drop_share, x1: bd.overall_drop_share,
      yref: "paper", y0: 0, y1: 1, line: { color: t.ink2, width: 1, dash: "dash" } }],
    annotations: bd.overall_drop_share == null ? [] : [{ x: bd.overall_drop_share, yref: "paper", y: 1.0, yanchor: "bottom",
      text: `avg ${pct(bd.overall_drop_share)}`, showarrow: false, font: { size: 10, color: t.muted } }],
  }));
}

/** Grouped bars comparing the answer distribution of No-drop vs Drop students. */
export function profileBars(el, prof) {
  const t = theme();
  const colors = [t.noDrop, t.drop];
  draw(el, prof.series.map((s, i) => ({
    type: "bar", name: `${s.class} (n=${s.n}${s.mean != null ? `, mean ${s.mean.toFixed(2)}` : ""})`,
    x: prof.labels, y: s.shares, marker: { color: colors[i], line: { color: t.surface, width: 2 } },
    hovertemplate: `<b>${esc(s.class)}</b><br>%{x}: %{y:.0%} of students<extra></extra>`,
  })), layout(t, { height: 260, showlegend: true, bargroupgap: 0.08, margin: { l: 8, r: 10, t: 34, b: 30 },
    yaxis: { tickformat: ".0%" }, xaxis: { type: "category", gridcolor: "rgba(0,0,0,0)" } }));
}

/** Diverging bars for risk signals: lift above 1 (raises risk) vs below 1 (lowers risk). */
export function liftBars(el, signals) {
  const t = theme();
  const rows = [...signals];
  draw(el, [{
    type: "bar", orientation: "h", y: rows.map((s) => wrap(`${s.question}: ${s.answer}`, 44)),
    x: rows.map((s) => s.lift - 1), base: 1,
    marker: { color: rows.map((s) => (s.lift >= 1 ? t.risk : t.protective)) },
    text: rows.map((s) => `${s.lift.toFixed(2)}×`), textposition: "outside", cliponaxis: false,
    textfont: { color: t.ink2, size: 11 },
    customdata: rows.map((s) => [s.drop_share, s.n]),
    hovertemplate: "<b>%{y}</b><br>Lift %{text}<br>Drop share %{customdata[0]:.0%} of %{customdata[1]} respondents<extra></extra>",
  }], layout(t, {
    height: 40 + rows.length * 38, margin: { l: 8, r: 44, t: 8, b: 30 },
    xaxis: { title: { text: "Lift vs average drop share (1× = average)" }, ticksuffix: "×", zeroline: false },
    yaxis: { autorange: "reversed", gridcolor: "rgba(0,0,0,0)", tickfont: { size: 11, color: t.ink2 } },
    shapes: [{ type: "line", x0: 1, x1: 1, yref: "paper", y0: 0, y1: 1, line: { color: t.ink2, width: 1 } }],
  }));
}

/** Heatmap of drop share for two questions (sequential, one hue). */
export function heatmap(el, ct) {
  const t = theme();
  const text = ct.drop_share.map((row, i) => row.map((v, j) => (v == null ? "" : `${pct(v)}<br><span style="font-size:10px">n=${ct.n[i][j]}</span>`)));
  draw(el, [{
    type: "heatmap", z: ct.drop_share, x: ct.col_labels, y: ct.row_labels, zmin: 0, zmax: 1, xgap: 2, ygap: 2,
    colorscale: t.seq.map((c, i) => [i / (t.seq.length - 1), c]),
    text, texttemplate: "%{text}", textfont: { size: 11 },
    customdata: ct.n, hovertemplate: `<b>${esc(ct.row_title)}: %{y}</b><br>${esc(ct.col_title)}: %{x}<br>Drop share %{z:.0%} (n=%{customdata})<extra></extra>`,
    colorbar: { title: { text: "Drop share", side: "right", font: { color: t.ink2, size: 11 } }, tickformat: ".0%",
      thickness: 10, outlinewidth: 0, tickfont: { color: t.muted, size: 10 } },
    hoverongaps: false,
  }], layout(t, { height: 90 + ct.row_labels.length * 46, margin: { l: 8, r: 8, t: 8, b: 40 },
    xaxis: { title: { text: ct.col_title }, type: "category", gridcolor: "rgba(0,0,0,0)" },
    yaxis: { title: { text: ct.row_title }, type: "category", autorange: "reversed", gridcolor: "rgba(0,0,0,0)" } }));
}

/** Generic grouped bars. series: [{name, values, color}], values in [0,1] when percent. */
export function groupedBars(el, { categories, series, percent = true, height = 280, horizontal = false, labels = true }) {
  const t = theme();
  const fmt = (v) => (v == null ? "" : percent ? pct(v) : Number(v).toFixed(2));
  draw(el, series.map((s) => ({
    type: "bar", name: s.name, orientation: horizontal ? "h" : "v",
    [horizontal ? "y" : "x"]: categories, [horizontal ? "x" : "y"]: s.values,
    marker: { color: s.color, line: { color: t.surface, width: 2 } },
    text: labels ? s.values.map(fmt) : undefined, textposition: "outside", cliponaxis: false,
    textfont: { size: 10, color: t.ink2 },
    hovertemplate: `<b>${esc(s.name)}</b><br>%{${horizontal ? "y" : "x"}}: %{${horizontal ? "x" : "y"}${percent ? ":.1%" : ":.3f"}}<extra></extra>`,
  })), layout(t, {
    height, showlegend: series.length > 1, bargroupgap: 0.08, margin: { l: 8, r: 30, t: series.length > 1 ? 36 : 12, b: 30 },
    [horizontal ? "xaxis" : "yaxis"]: { tickformat: percent ? ".0%" : "", rangemode: "tozero" },
    [horizontal ? "yaxis" : "xaxis"]: { type: "category", gridcolor: "rgba(0,0,0,0)", ...(horizontal ? { autorange: "reversed" } : {}) },
  }));
}

/** Simple horizontal bars, one hue. */
export function barH(el, { labels, values, color, text, hover, xTitle = "", height }) {
  const t = theme();
  draw(el, [{
    type: "bar", orientation: "h", y: labels.map((l) => wrap(l, 40)), x: values,
    marker: { color: color || t.noDrop }, text, textposition: "outside", cliponaxis: false,
    textfont: { size: 10, color: t.ink2 }, hovertext: hover, hoverinfo: hover ? "text" : "x+y",
  }], layout(t, { height: height || 40 + labels.length * 26, margin: { l: 8, r: 50, t: 8, b: 34 },
    xaxis: { title: { text: xTitle } }, yaxis: { autorange: "reversed", gridcolor: "rgba(0,0,0,0)", tickfont: { size: 11, color: t.ink2 } } }));
}

/** ROC curves: the highlighted model in accent blue, others recede in gray. */
export function rocChart(el, models, highlight) {
  const t = theme();
  const order = [...models.filter((m) => m.model !== highlight), ...models.filter((m) => m.model === highlight)];
  draw(el, [
    { x: [0, 1], y: [0, 1], mode: "lines", line: { color: t.axis, dash: "dash", width: 1 }, hoverinfo: "skip", showlegend: false },
    ...order.filter((m) => m.roc).map((m) => ({
      x: m.roc.fpr, y: m.roc.tpr, mode: "lines", name: `${m.label} (AUC ${m.roc.auc.toFixed(3)})`,
      line: { color: m.model === highlight ? t.noDrop : t.neutral, width: m.model === highlight ? 3 : 1.5, shape: "hv" },
      hovertemplate: `<b>${esc(m.label)}</b><br>FPR %{x:.2f} · TPR %{y:.2f}<extra></extra>`,
    })),
  ], layout(t, { height: 320, showlegend: true, legend: { x: 1, xanchor: "right", y: 0.02, yanchor: "bottom", traceorder: "reversed", font: { size: 11, color: t.ink2 } },
    xaxis: { title: { text: "False positive rate" }, range: [-0.01, 1.01] },
    yaxis: { title: { text: "True positive rate" }, range: [-0.01, 1.03] } }));
}

export function confusion(el, matrix) {
  const t = theme();
  const labels = ["No drop", "Drop"];
  const max = Math.max(...matrix.flat());
  draw(el, [{
    type: "heatmap", z: matrix, x: labels, y: labels, zmin: 0, zmax: max, xgap: 3, ygap: 3, showscale: false,
    colorscale: t.seq.map((c, i) => [i / (t.seq.length - 1), c]),
    text: matrix.map((r) => r.map(String)), texttemplate: "<b>%{text}</b>", textfont: { size: 16 },
    hovertemplate: "Actual %{y} · Predicted %{x}: %{z} students<extra></extra>",
  }], layout(t, { height: 250, margin: { l: 8, r: 8, t: 8, b: 40 },
    xaxis: { title: { text: "Predicted" }, type: "category", gridcolor: "rgba(0,0,0,0)" },
    yaxis: { title: { text: "Actual" }, type: "category", autorange: "reversed", gridcolor: "rgba(0,0,0,0)" } }));
}
