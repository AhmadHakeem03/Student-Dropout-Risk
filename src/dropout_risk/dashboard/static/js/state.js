// Global view state: data source + segment filters, shared by every dashboard.
const KEY = "dropout-dashboards:v1";
const listeners = new Set();

export const state = { source: null, filters: {}, theme: "system" };

try {
  Object.assign(state, JSON.parse(localStorage.getItem(KEY) || "{}"));
} catch { /* storage unavailable: start fresh */ }

function save() {
  try { localStorage.setItem(KEY, JSON.stringify(state)); } catch { /* ignore */ }
}

export function update(patch) {
  Object.assign(state, patch);
  save();
  listeners.forEach((fn) => fn(state));
}

export function onChange(fn) { listeners.add(fn); }

/** Query params understood by every analytics endpoint. */
export function params({ withSource = true } = {}) {
  const f = Object.entries(state.filters).filter(([, v]) => v !== "" && v != null).map(([k, v]) => `${k}:${v}`);
  return withSource ? { source: state.source, f } : { f };
}

export function activeFilterCount() {
  return Object.values(state.filters).filter((v) => v !== "" && v != null).length;
}
