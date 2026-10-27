import { post } from "../api.js";
import { barH, theme } from "../charts.js";
import { card, chip, el, empty, esc, grid, pct, showError } from "../ui.js";

export default {
  id: "simulator",
  title: "Risk simulator",
  subtitle: "Enter a student's answers to get a dropout-risk score and the changes that would lower it most.",
  filters: "none",
  async render(root, { meta }) {
    if (!meta.model_ready) {
      root.innerHTML = '<div class="card empty">No trained model yet. Run <code>uv run dropout-risk</code>, then reload.</div>';
      return;
    }
    const defaults = (await post("/predict", { answers: {} })).answers_used;
    const g = grid(root);
    const form = card(g, { title: "Student answers", sub: "Pre-filled with the most common answer to each question", chart: false });
    const res = card(g, { title: "Predicted risk", chart: false });
    const drv = card(grid(root), { title: "Action plan: what would reduce this student's risk", span: 2,
      sub: "Step by step, each bar is the predicted probability after this change and all the changes above it (actionable questions only)" });

    form.body.innerHTML = meta.groups.map((group) => {
      const feats = meta.features.filter((f) => f.group === group);
      return `<div class="form-group"><h3>${esc(group)}</h3><div class="form-grid">${feats.map((f) => `
        <label class="field" for="q-${f.name}">${esc(f.title)}
          <select id="q-${f.name}" data-feature="${f.name}">${f.answers.map((a) =>
            `<option value="${a.code}" ${a.code === defaults[f.name] ? "selected" : ""}>${esc(a.label)}</option>`).join("")}</select>
        </label>`).join("")}</div></div>`;
    }).join("") + '<div class="toolbar" style="margin-top:14px"><button class="btn" type="button" id="sim-reset">Reset to defaults</button></div>';

    const t = theme();
    let seq = 0;
    const score = async () => {
      const answers = Object.fromEntries([...form.body.querySelectorAll("select")].map((s) => [s.dataset.feature, Number(s.value)]));
      const mine = ++seq;
      try {
        const r = await post("/predict", { answers });
        if (mine !== seq) return; // a newer request superseded this one
        res.body.innerHTML = "";
        res.body.appendChild(el(`<div>
          <div class="kpi"><div class="value" style="font-size:44px">${pct(r.probability)}</div>
          <div class="note">${chip(r.band)} · model: ${esc(r.model.replace(/_/g, " "))}</div></div>
          <div class="gauge" role="img" aria-label="Risk ${pct(r.probability)}"><div class="marker" style="left:${r.probability * 100}%"></div></div>
          <div class="gauge-scale"><span>0%</span><span>medium ≥ ${pct(r.risk_bands.medium)}</span><span>high ≥ ${pct(r.risk_bands.high)}</span><span>100%</span></div>
        </div>`));
        const d = r.what_would_reduce_risk;
        if (!d.length) return empty(drv.body, "This student's answers are already at their lowest-risk options.");
        barH(drv.body, {
          labels: d.map((x, i) => `${i + 1}. ${x.question}: ${x.current} → ${x.suggested}`),
          values: d.map((x) => x.probability_if_changed), color: t.protective,
          text: d.map((x) => pct(x.probability_if_changed)),
          hover: d.map((x) => `${esc(x.question)}<br>${esc(x.current)} → ${esc(x.suggested)}<br>Cumulative risk after this step: ${pct(x.probability_if_changed)}`),
          xTitle: "Predicted drop probability after the change",
        });
      } catch (e) { showError(res.body, e); }
    };
    form.body.querySelectorAll("select").forEach((s) => s.addEventListener("change", score));
    form.body.querySelector("#sim-reset").addEventListener("click", () => {
      form.body.querySelectorAll("select").forEach((s) => { s.value = defaults[s.dataset.feature]; });
      score();
    });
    await score();
  },
};
