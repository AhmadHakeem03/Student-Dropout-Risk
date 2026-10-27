// Thin client for the dashboard API. The base path is injected by the server (<meta name="api-base">),
// so the same files work wherever the host FastAPI app mounts the router.
const BASE = (document.querySelector('meta[name="api-base"]')?.content || "/api/dropout").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

export function apiUrl(path, params = {}) {
  const url = new URL(BASE + path, location.origin);
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    (Array.isArray(value) ? value : [value]).forEach((v) => url.searchParams.append(key, v));
  }
  return url;
}

async function handle(res) {
  if (res.ok) return res.json();
  let detail = res.statusText;
  try { detail = (await res.json()).detail ?? detail; } catch { /* non-JSON error */ }
  throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
}

const cache = new Map();

export async function get(path, params = {}) {
  const url = apiUrl(path, params).toString();
  if (!cache.has(url)) cache.set(url, fetch(url).then(handle).catch((e) => { cache.delete(url); throw e; }));
  return cache.get(url);
}

export async function post(path, body) {
  const res = await fetch(apiUrl(path), {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  return handle(res);
}
