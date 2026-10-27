import { get } from "../api.js";
import { barH, liftBars, theme } from "../charts.js";
import { barCell, card, empty, esc, grid, lift, pct, showError, table } from "../ui.js";

export default {
  id: "drivers",
  title: "Risk drivers",
  subtitle: "Which answers raise or lower dropout risk, and what the prediction model relies on.",
  filters: "all",
  async render(root, { meta, params }) {
    const signals = await get("/risk-signals", params());
    const t = theme();

    const g = grid(root);
    const r = card(g, { title: "Answers that raise risk", sub: "Top 12 by lift · actionable answers are ones the institution can influence" });
    signals.risk.length ? liftBars(r.body, signals.risk.slice(0, 12)) : empty(r.body);
    const pr = card(g, { title: "Answers that lower risk", sub: "Top 12 protective answers" });
    signals.protective.length ? liftBars(pr.body, signals.protective.slice(0, 12)) : empty(pr.body);

    const all = [...signals.risk, ...signals.protective].sort((a, b) => b.lift - a.lift);
    const maxLift = Math.max(...all.map((s) => s.lift), 1);
    const tc = card(grid(root), { title: "All risk signals", span: 2, chart: false,
      sub: `${all.length} answers given by at least ${signals.min_n} respondents · average drop share ${pct(signals.overall_drop_share)}`,
      actions: `<label class="field"><span><input type="checkbox" id="only-actionable"> Actionable only</span></label>` });
    const drawTable = () => {
      const only = tc.card.querySelector("#only-actionable").checked;
      const rows = all.filter((s) => !only || s.actionable);
      tc.body.innerHTML = table([
        { key: "group", label: "Area" },
        { key: "question", label: "Question" },
        { key: "answer", label: "Answer" },
        { key: "n", label: "Respondents", num: true },
        { key: "drop_share", label: "Drop share", num: true, render: (s) => pct(s.drop_share) },
        { key: "lift", label: "Lift", render: (s) => barCell(s.lift, maxLift, s.lift >= 1 ? t.risk : t.protective, lift(s.lift)) },
        { key: "actionable", label: "Actionable", render: (s) => (s.actionable ? "Yes" : '<span class="tag">No</span>') },
      ], rows);
    };
    tc.card.querySelector("#only-actionable").addEventListener("change", drawTable);
    drawTable();

    if (!meta.model_ready) return;
    const mg = grid(root);
    const ic = card(mg, { title: "What the model relies on", sub: "Drop in test ROC-AUC when one survey answer is shuffled (permutation importance)" });
    const sc = card(mg, { title: "Feature selection ranking", sub: "Combined mutual-information + random-forest score · blue = used by the model" });
    try {
      const imp = await get("/model/importance");
      const top = imp.permutation.filter((x) => x.mean > 0).slice(0, 12);
      barH(ic.body, { labels: top.map((x) => x.title), values: top.map((x) => x.mean), color: t.noDrop,
        text: top.map((x) => x.mean.toFixed(3)), hover: top.map((x) => `${esc(x.title)}<br>ΔAUC ${x.mean.toFixed(3)} ± ${x.std.toFixed(3)}`),
        xTitle: "Δ ROC-AUC" });
      const sel = imp.selection.filter((x) => x.score != null).slice(0, 20);
      barH(sc.body, { labels: sel.map((x) => x.title), values: sel.map((x) => x.score),
        color: sel.map((x) => (x.status === "selected" ? t.noDrop : t.neutral)),
        text: sel.map((x) => x.score.toFixed(2)), hover: sel.map((x) => `${esc(x.title)}<br>${esc(x.status)}`), xTitle: "Score" });
    } catch (e) { showError(ic.body, e); showError(sc.body, e); }
  },
};
