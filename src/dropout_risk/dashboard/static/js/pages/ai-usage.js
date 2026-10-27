import { get } from "../api.js";
import { groupedBars, theme } from "../charts.js";
import { card, grid, showError } from "../ui.js";
import { breakdownGrid, profileCard } from "./common.js";

const TOOLS = ["uses_chatgpt", "uses_gemini", "uses_claude", "uses_copilot", "uses_other_tool"];

export default {
  id: "ai-usage",
  title: "AI usage & literacy",
  subtitle: "How intensively students use AI tools, which tools, and how well they understand them.",
  filters: "all",
  async render(root, { params }) {
    const t = theme();
    const g = grid(root);
    const adoption = card(g, { title: "AI tool adoption by class", sub: "Share of each class using the tool" });
    const risk = card(g, { title: "Drop share among tool users", sub: "Of students who use the tool, share in the drop class" });
    try {
      const { tools } = await get("/tools", params());
      groupedBars(adoption.body, { categories: tools.map((x) => x.title), series: [
        { name: "No drop", values: tools.map((x) => x.adoption["No drop"]), color: t.noDrop },
        { name: "Drop", values: tools.map((x) => x.adoption["Drop"]), color: t.drop },
      ] });
      groupedBars(risk.body, { categories: tools.map((x) => `${x.title} (n=${x.users})`),
        series: [{ name: "Drop share", values: tools.map((x) => x.drop_share_among_users), color: t.drop }], horizontal: true, height: 240 });
    } catch (e) { showError(adoption.body, e); showError(risk.body, e); }

    const p = grid(root);
    await Promise.all([
      profileCard(p, "ai_search_substitution", params, { title: "AI replacing search & research" }),
      profileCard(p, "ai_literacy", params, { title: "AI literacy score" }),
      profileCard(p, "n_ai_tools", params, { title: "Number of AI tools used" }),
    ]);
    await breakdownGrid(root, "AI usage", params, { exclude: TOOLS });
    await breakdownGrid(root, "AI literacy", params);
  },
};
