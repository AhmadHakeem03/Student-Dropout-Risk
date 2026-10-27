import { get } from "../api.js";
import { liftBars, shareBars } from "../charts.js";
import { card, chip, empty, esc, grid, kpi, num, pct, showError } from "../ui.js";
import { insight, profileCard } from "./common.js";

export default {
  id: "overview",
  title: "Executive overview",
  subtitle: "Headline dropout risk, who is most affected, and the answers that signal risk.",
  filters: "all",
  async render(root, { meta, params }) {
    const p = params();
    const [k, signals] = await Promise.all([get("/kpis", p), get("/risk-signals", { ...p, limit: 5 })]);
    const [wl, perf] = meta.model_ready
      ? await Promise.all([get("/watchlist", { ...params({ withSource: false }), limit: 1 }), get("/model/performance")])
      : [null, null];

    const tiles = grid(root, "kpis");
    kpi(tiles, { label: "Rows in view", value: num(k.rows),
      note: k.rows === k.rows_total ? `${pct(k.synthetic_share)} synthetic` : `of ${num(k.rows_total)} · ${pct(k.synthetic_share)} synthetic` });
    kpi(tiles, { label: "Drop share", value: pct(k.drop_share, 1),
      note: k.rows === k.rows_total ? `${num(k.drop_count)} students in the drop class` : `vs ${pct(k.drop_share_total, 1)} for the whole source` });
    if (wl) {
      kpi(tiles, { label: "High-risk surveyed students", value: num(wl.band_counts.high),
        note: `${chip("high")} of ${num(wl.rows)} surveyed students (model score ≥ ${pct(wl.risk_bands.high)})` });
      const best = perf.models.find((m) => m.model === perf.best_model);
      kpi(tiles, { label: "Early-warning model", value: esc(best.label),
        note: `catches ${pct(best.test.recall)} of drop students · F1 ${best.test.f1.toFixed(2)} on held-out data` });
    }

    const top = grid(root);
    const ins = card(top, { title: "Key findings", sub: "Strongest signals in the current view", chart: false });
    const lines = [...signals.risk.slice(0, 3), ...signals.protective.slice(0, 2)];
    ins.body.innerHTML = lines.length ? `<ul class="insights">${lines.map((s) => insight(s, signals.overall_drop_share)).join("")}</ul>` : "";
    if (!lines.length) empty(ins.body);
    const lb = card(top, { title: "Top risk & protective signals", sub: `Lift = drop share among students giving the answer ÷ average · min ${signals.min_n} respondents` });
    const rows = [...signals.risk.slice(0, 5), ...signals.protective.slice(0, 5).reverse()];
    if (rows.length) liftBars(lb.body, rows); else empty(lb.body);

    const seg = grid(root);
    for (const feature of ["major", "study_year"]) {
      const c = card(seg, { title: "", sub: "Drop share by answer · dashed line = average" });
      get(`/breakdown/${feature}`, p).then((bd) => {
        c.card.querySelector("h2").textContent = `Drop share by ${bd.title.toLowerCase()}`;
        bd.rows_total ? shareBars(c.body, bd) : empty(c.body);
      }).catch((e) => showError(c.body, e));
    }
    const prof = grid(root);
    await Promise.all([
      profileCard(prof, "ai_dependency_index", params, { title: "AI dependency: drop vs no-drop students" }),
      profileCard(prof, "integrity_risk_count", params, { title: "Integrity incidents: drop vs no-drop students" }),
    ]);
  },
};
