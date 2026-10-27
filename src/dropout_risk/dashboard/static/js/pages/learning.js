import { grid } from "../ui.js";
import { breakdownGrid, crosstabCard, profileCard } from "./common.js";

export default {
  id: "learning",
  title: "Learning impact",
  subtitle: "How students say AI affects their thinking, motivation and independence — and how that relates to dropout.",
  filters: "all",
  async render(root, { meta, params }) {
    const p = grid(root);
    await Promise.all([
      profileCard(p, "negative_impact_count", params, { title: "Negative learning effects" }),
      profileCard(p, "perceived_benefit", params, { title: "Perceived benefit of AI" }),
    ]);
    await crosstabCard(grid(root), meta, params, { row: "over_reliance", col: "motivation_effect", title: "Over-reliance × motivation" });
    await breakdownGrid(root, "Learning impact", params);
  },
};
