const TOKEN_KEY = "kgl_token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* private mode: stay signed in for this tab only */
  }
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const res = await fetch(`/api${path}`, { method, headers, body: payload });
  if (res.status === 401 && !path.startsWith("/auth/login")) {
    setToken(null);
    window.location.assign("/login");
  }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const detail = Array.isArray(data.detail) ? data.detail.map((d: { msg: string }) => d.msg).join("; ") : data.detail;
    throw new ApiError(res.status, detail || `Something went wrong (${res.status}).`);
  }
  if (res.status === 204) return undefined as T;
  const type = res.headers.get("content-type") || "";
  return (type.includes("application/json") ? res.json() : res.blob()) as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  put: <T>(path: string, body: unknown) => request<T>("PUT", path, body),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
  del: (path: string) => request<void>("DELETE", path),
};

/** Drop empty values so saved filters stay readable. */
export function cleanFilters<T extends object>(f: T): Partial<T> {
  return Object.fromEntries(
    Object.entries(f).filter(([, v]) => !(v === "" || v === undefined || v === null || v === false || (Array.isArray(v) && !v.length))),
  ) as Partial<T>;
}
