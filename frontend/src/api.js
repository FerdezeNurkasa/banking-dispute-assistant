const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";
const SESSION_KEY = "dispute-session";

// The session (token + user) lives in sessionStorage: it survives a page refresh but is
// cleared when the tab closes. (In production an httpOnly cookie is even safer.)
function readSession() {
  try {
    return JSON.parse(sessionStorage.getItem(SESSION_KEY));
  } catch {
    return null;
  }
}

let session = readSession();

export function getSession() {
  return session;
}

export function setSession(value) {
  session = value;
  try {
    if (value) sessionStorage.setItem(SESSION_KEY, JSON.stringify(value));
    else sessionStorage.removeItem(SESSION_KEY);
  } catch {
    /* storage can be unavailable (private mode); the in-memory session still works */
  }
}

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(session ? { Authorization: `Bearer ${session.token}` } : {}),
      ...options.headers,
    },
  });
  if (res.status === 401 && session && path !== "/auth/login") {
    setSession(null);
    window.dispatchEvent(new Event("auth:logout")); // token expired or user deactivated
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = Array.isArray(body.detail) ? body.detail.map((d) => d.msg).join(", ") : body.detail;
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return res.json();
}

const post = (path, data) => request(path, { method: "POST", body: JSON.stringify(data) });

export const api = {
  login: async (username, password) => {
    const data = await post("/auth/login", { username, password });
    const value = { token: data.access_token, user: data.user };
    setSession(value);
    return value;
  },
  customers: () => request("/customers"),
  disputes: (status) => request(`/disputes${status ? `?status=${status}` : ""}`),
  dispute: (id) => request(`/disputes/${id}`),
  create: (data) => post("/disputes", data),
  review: (id, data) => post(`/disputes/${id}/review`, data),
  search: (q) => request(`/search?q=${encodeURIComponent(q)}`),
  analytics: () => request("/analytics"),
};