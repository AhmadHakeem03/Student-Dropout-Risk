import { get } from "../api.js";
import { theme } from "../charts.js";
import { barCell, card, chip, empty, esc, grid, kpi, num, pct, select, table } from "../ui.js";

export default {
  id: "watchlist",
  title: "Early-warning watchlist",
  subtitle: "Surveyed students ranked by the model's predicted dropout probability, with the signals behind each score.",
  filters: "segments",
  note: "Scores come from the best model applied to the 183 surveyed students. Students marked “in training” were used to fit the model, so their scores are optimistic.",
  async render(root, { meta, params }) {
    if (!meta.model_ready) {
      root.innerHTML = '<div class="card empty">No trained model yet. Run <code>uv run dropout-risk</code>, then reload.</div>';
      return;
    }
    const base = params({ withSource: false });
    const summary = await get("/watchlist", { ...base, limit: 1 });
    const tiles = grid(root, "kpis");
    const b = summary.risk_bands;
    kpi(tiles, { label: "Students scored", value: num(summary.rows), note: "after segment filters" });
    kpi(tiles, { label: "High risk", value: num(summary.band_counts.high), note: `${chip("high")} probability ≥ ${pct(b.high)}` });
    kpi(tiles, { label: "Medium risk", value: num(summary.band_counts.medium), note: `${chip("medium")} ${pct(b.medium)} – ${pct(b.high)}` });
    kpi(tiles, { label: "Low risk", value: num(summary.band_counts.low), note: `${chip("low")} below ${pct(b.medium)}` });

    const t = theme();
    const controls = `<div class="toolbar">${select("wl-band", "Risk band", [{ value: "", label: "All bands" },
      { value: "high", label: "High" }, { value: "medium", label: "Medium" }, { value: "low", label: "Low" }], "")}
      ${select("wl-limit", "Show", [25, 50, 100, 200].map((n) => ({ value: n, label: `Top ${n}` })), 25)}</div>`;
    const c = card(grid(root), { title: "Students to follow up", span: 2, chart: false, actions: controls,
      sub: "Signals = the student's answers with the highest drop-risk lift in the survey" });
    const load = async () => {
      const band = c.card.querySelector("#wl-band").value;
      const limit = c.card.querySelector("#wl-limit").value;
      const data = await get("/watchlist", { ...base, band, limit });
      if (!data.students.length) return empty(c.body);
      c.body.innerHTML = table([
        { key: "respondent_id", label: "Respondent", num: true },
        { key: "probability", label: "Drop probability", render: (s) => barCell(s.probability, 1, s.band === "high" ? t.risk : s.band === "medium" ? "var(--warning)" : "var(--good)", pct(s.probability)) },
        { key: "band", label: "Band", render: (s) => chip(s.band) },
        { key: "major", label: "Major" },
        { key: "study_year", label: "Year" },
        { key: "gender", label: "Gender" },
        { key: "university", label: "University" },
        { key: "signals", label: "Top risk signals", render: (s) => (s.signals.length ? `<ul class="signals">${s.signals.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : '<span class="tag">none</span>') },
        { key: "recorded_drop", label: "Recorded", render: (s) => (s.recorded_drop ? "Drop" : "No drop") },
        { key: "in_training", label: "Set", render: (s) => `<span class="tag">${s.in_training ? "in training" : "held-out"}</span>` },
      ], data.students);
    };
    c.card.querySelectorAll("select").forEach((s) => s.addEventListener("change", load));
    await load();
  },
};
