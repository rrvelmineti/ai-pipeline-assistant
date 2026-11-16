// Small client for the platform API. The session token lives in sessionStorage, so closing the tab signs out.
const KEY = "claims-platform-token";

function readToken(): string | null {
  try {
    return sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
}

let token: string | null = readToken();
let onSignedOut: () => void = () => {};

export function setToken(value: string | null) {
  token = value;
  try {
    if (value) sessionStorage.setItem(KEY, value);
    else sessionStorage.removeItem(KEY);
  } catch {
    /* storage unavailable: the session lasts until the page is reloaded */
  }
}

export function hasToken() {
  return token !== null;
}

export function whenSignedOut(callback: () => void) {
  onSignedOut = callback;
}

export class ApiError extends Error {
  status: number;
  fields: string[];
  constructor(status: number, message: string, fields: string[] = []) {
    super(message);
    this.status = status;
    this.fields = fields;
  }
}

function detailMessage(detail: unknown): { message: string; fields: string[] } {
  if (typeof detail === "string") return { message: detail, fields: [] };
  if (Array.isArray(detail)) {
    return { message: detail.map((d) => (d && typeof d === "object" && "msg" in d ? String(d.msg) : String(d))).join(" "), fields: [] };
  }
  if (detail && typeof detail === "object") {
    const d = detail as { message?: string; unconfirmed_fields?: string[] };
    return { message: d.message ?? "The request was refused.", fields: d.unconfirmed_fields ?? [] };
  }
  return { message: "The request failed.", fields: [] };
}

type Options = { method?: string; json?: unknown; form?: FormData };

async function send(path: string, opts: Options = {}): Promise<Response> {
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (opts.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.json);
  } else if (opts.form) {
    body = opts.form;
  }
  const res = await fetch(path, { method: opts.method ?? (body ? "POST" : "GET"), headers, body });
  if (res.status === 401 && token) {
    setToken(null);
    onSignedOut();
  }
  if (!res.ok) {
    let parsed: { message: string; fields: string[] } = { message: `${res.status} ${res.statusText}`, fields: [] };
    try {
      parsed = detailMessage((await res.json()).detail);
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, parsed.message, parsed.fields);
  }
  return res;
}

export async function api<T>(path: string, opts: Options = {}): Promise<T> {
  const res = await send(path, opts);
  const type = res.headers.get("content-type") ?? "";
  return (type.includes("application/json") ? res.json() : res.text()) as Promise<T>;
}

export async function download(path: string, filename: string) {
  const res = await send(path);
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
