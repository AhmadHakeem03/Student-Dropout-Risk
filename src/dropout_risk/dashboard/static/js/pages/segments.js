import { grid } from "../ui.js";
import { breakdownGrid, crosstabCard } from "./common.js";

export default {
  id: "segments",
  title: "Student segments",
  subtitle: "Dropout risk across majors, study years, gender, residence and university type.",
  filters: "all",
  async render(root, { meta, params }) {
    await crosstabCard(grid(root), meta, params, { row: "major", col: "study_year", title: "Risk hot-spots by segment" });
    await breakdownGrid(root, "Demographics", params);
  },
};
