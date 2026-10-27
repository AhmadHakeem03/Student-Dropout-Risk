import { get } from "../api.js";
import { confusion, groupedBars, rocChart, theme } from "../charts.js";
import { card, esc, grid, kpi, pct, select, table } from "../ui.js";

export default {
  id: "model",
  title: "Model performance",
  subtitle: "How the five candidate models compare, and how reliable the selected early-warning model is.",
  filters: "none",
  async render(root, { meta }) {
    if (!meta.model_ready) {
      root.innerHTML = '<div class="card empty">No trained model yet. Run <code>uv run dropout-risk</code>, then reload.</div>';
      return;
    }
    const perf = await get("/model/performance");
    const t = theme();
    const best = perf.models.find((m) => m.model === perf.best_model);
    const tiles = grid(root, "kpis");
    kpi(tiles, { label: "Selected model", value: esc(best.label), note: "highest cross-validated F1" });
    kpi(tiles, { label: "Drop students caught (recall)", value: pct(best.test.recall), note: `on ${perf.test_rows} held-out students (${perf.test_drop} drop)` });
    kpi(tiles, { label: "Precision", value: pct(best.test.precision), note: "of flagged students who are in the drop class" });
    kpi(tiles, { label: "Test F1", value: best.test.f1.toFixed(2),
      note: `95% CI ${best.test_f1_ci.map((x) => x.toFixed(2)).join("–")} · always-flag baseline ${perf.baseline_f1_always_drop.toFixed(2)}` });

    const g = grid(root);
    const cmp = card(g, { title: "F1 by model", sub: "Cross-validation on training data vs held-out test data" });
    const ordered = [...perf.models].sort((a, b) => b.cv.f1 - a.cv.f1);
    groupedBars(cmp.body, { categories: ordered.map((m) => m.label), percent: false, height: 300, series: [
      { name: "Cross-validation F1", values: ordered.map((m) => m.cv.f1), color: t.real },
      { name: "Test F1", values: ordered.map((m) => m.test.f1), color: t.synthetic },
    ] });
    const roc = card(g, { title: "ROC curves (held-out test set)", sub: "Selected model highlighted" });
    rocChart(roc.body, perf.models, perf.best_model);

    const g2 = grid(root);
    const metricCols = [["f1", "F1"], ["roc_auc", "ROC-AUC"], ["recall", "Recall"], ["precision", "Precision"], ["accuracy", "Accuracy"]];
    const tc = card(g2, { title: "All metrics", span: 2, chart: false, sub: "CV = mean of 5-fold × 3 repeats; Test = held-out students" });
    tc.body.innerHTML = table([
      { key: "label", label: "Model", render: (m) => `${esc(m.label)}${m.model === perf.best_model ? " ★" : ""}` },
      ...metricCols.map(([k, l]) => ({ key: `cv_${k}`, label: `CV ${l}`, num: true, render: (m) => m.cv[k].toFixed(3) })),
      ...metricCols.map(([k, l]) => ({ key: `test_${k}`, label: `Test ${l}`, num: true, render: (m) => m.test[k].toFixed(3) })),
    ], ordered, { rowClass: (m) => (m.model === perf.best_model ? "best" : "") });

    const opts = perf.models.map((m) => ({ value: m.model, label: m.label }));
    const cm = card(g2, { title: "Confusion matrix", sub: "Held-out students at a 50% threshold",
      actions: `<div class="toolbar">${select("cm-model", "Model", opts, perf.best_model)}</div>` });
    const drawCm = () => confusion(cm.body, perf.models.find((m) => m.model === cm.card.querySelector("#cm-model").value).confusion);
    cm.card.querySelector("#cm-model").addEventListener("change", drawCm);
    drawCm();
  },
};
