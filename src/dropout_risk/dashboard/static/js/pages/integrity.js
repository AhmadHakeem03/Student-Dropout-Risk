import { grid } from "../ui.js";
import { breakdownGrid, crosstabCard, profileCard } from "./common.js";

export default {
  id: "integrity",
  title: "Academic integrity",
  subtitle: "AI use in assessed work and exams, professor flags, and content review habits.",
  filters: "all",
  async render(root, { meta, params }) {
    const p = grid(root);
    await Promise.all([
      profileCard(p, "integrity_risk_count", params, { title: "Integrity incidents per student" }),
      profileCard(p, "detection_awareness", params, { title: "Awareness of AI detection" }),
    ]);
    await crosstabCard(grid(root), meta, params, { row: "flagged_by_professor", col: "submitted_full_project", title: "Professor flags × full AI projects" });
    await breakdownGrid(root, "Academic integrity", params);
  },
};
