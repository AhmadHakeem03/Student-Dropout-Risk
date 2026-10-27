import { get } from "../api.js";
import { barH, groupedBars, theme } from "../charts.js";
import { card, esc, grid, kpi, num, pct, select, showError } from "../ui.js";

export default {
  id: "quality",
  title: "Synthetic data quality",
  subtitle: "How closely the SMOTEN-generated rows match the real training respondents they were built from.",
  filters: "none",
  async render(root, { meta }) {
    const q = await get("/data-quality");
    const t = theme();
    const tiles = grid(root, "kpis");
    kpi(tiles, { label: "Real training rows", value: num(q.rows_real) });
    kpi(tiles, { label: "Synthetic rows", value: num(q.rows_synthetic), note: `${pct(q.rows_synthetic / (q.rows_real + q.rows_synthetic))} of the augmented set` });
    kpi(tiles, { label: "Distinct synthetic patterns", value: num(q.distinct_synthetic), note: `${pct(q.duplicate_share)} of synthetic rows repeat another` });
    kpi(tiles, { label: "Questions losing answers", value: num(q.features_losing_answers), note: `of ${q.features.length}: rare answers never appear in synthetic rows` });

    const g = grid(root);
    const cc = card(g, { title: "Class balance by data source", sub: "SMOTEN balances the classes in the training data" });
    const sources = Object.keys(q.class_counts);
    groupedBars(cc.body, { categories: sources, percent: false, height: 280, series: [
      { name: "No drop", values: sources.map((s) => q.class_counts[s]["No drop"]), color: t.noDrop },
      { name: "Drop", values: sources.map((s) => q.class_counts[s]["Drop"]), color: t.drop },
    ] });
    const tv = card(g, { title: "Distribution shift per question", sub: "Total variation distance, real vs synthetic answers (0 = identical, 1 = disjoint)" });
    const top = q.features.slice(0, 15);
    barH(tv.body, { labels: top.map((f) => f.title), values: top.map((f) => f.tvd), color: t.real,
      text: top.map((f) => f.tvd.toFixed(2)),
      hover: top.map((f) => `${esc(f.title)}<br>TVD ${f.tvd.toFixed(3)}<br>answers used: ${f.answers_real} real → ${f.answers_synthetic} synthetic`),
      xTitle: "Total variation distance" });

    const opts = meta.features.map((f) => ({ value: f.name, label: f.title }));
    const dc = card(grid(root), { title: "Real vs synthetic answers", span: 2, sub: "Share of rows giving each answer",
      actions: `<div class="toolbar">${select("dq-feature", "Question", opts, q.features[0].feature)}</div>` });
    const load = async () => {
      try {
        const d = await get(`/data-quality/${dc.card.querySelector("#dq-feature").value}`);
        groupedBars(dc.body, { categories: d.labels, height: 300, series: [
          { name: "Real", values: d.series[0].shares, color: t.real },
          { name: "Synthetic", values: d.series[1].shares, color: t.synthetic },
        ] });
      } catch (e) { showError(dc.body, e); }
    };
    dc.card.querySelector("#dq-feature").addEventListener("change", load);
    await load();
  },
};
