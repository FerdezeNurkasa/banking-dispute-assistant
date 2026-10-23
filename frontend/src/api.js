const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";
const API_KEY = import.meta.env.VITE_API_KEY;

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(API_KEY ? { "X-API-Key": API_KEY } : {}),
      ...options.headers,
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = Array.isArray(body.detail) ? body.detail.map((d) => d.msg).join(", ") : body.detail;
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return res.json();
}

export const api = {
  customers: () => request("/customers"),
  disputes: (status) => request(`/disputes${status ? `?status=${status}` : ""}`),
  dispute: (id) => request(`/disputes/${id}`),
  create: (data) => request("/disputes", { method: "POST", body: JSON.stringify(data) }),
  review: (id, data) => request(`/disputes/${id}/review`, { method: "POST", body: JSON.stringify(data) }),
  search: (q) => request(`/search?q=${encodeURIComponent(q)}`),
};