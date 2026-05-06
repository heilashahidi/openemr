/**
 * Thin fetch wrapper for OpenEMR's REST + FHIR R4 endpoints.
 *
 * The dashboard is a SPA; OpenEMR is the backend. We never call OpenEMR's
 * PHP pages — only its API endpoints. Auth: pass a bearer token that the
 * host page (or a parent iframe wrapper) supplies via URL/sessionStorage.
 */

const TOKEN_STORAGE_KEY = "openemr_dashboard_token";

/** Base path. Empty string in dev (Vite proxy); same-origin "" in prod. */
export const BASE: string =
  (import.meta as ImportMeta & { env?: Record<string, string> }).env
    ?.VITE_OPENEMR_BASE ?? "";

export class FhirError extends Error {
  constructor(message: string, public status: number, public body?: unknown) {
    super(message);
  }
}

/** Stash the OAuth bearer token so subsequent fetches reuse it. */
export function setToken(token: string): void {
  sessionStorage.setItem(TOKEN_STORAGE_KEY, token);
}

export function getToken(): string | null {
  // For demo: also accept a token via ?access_token=... in the URL so the
  // OpenEMR iframe wrapper can pass one in without a token-exchange flow.
  const url = new URL(window.location.href);
  const fromUrl = url.searchParams.get("access_token");
  if (fromUrl) {
    setToken(fromUrl);
    // Clean it from the URL so it's not visible in browser history / share.
    url.searchParams.delete("access_token");
    window.history.replaceState({}, "", url.toString());
    return fromUrl;
  }
  return sessionStorage.getItem(TOKEN_STORAGE_KEY);
}

interface FetchOptions {
  signal?: AbortSignal;
  /** REST endpoints under /apis/default/api; FHIR under /apis/default/fhir. */
  flavor?: "fhir" | "rest";
}

/**
 * Fetch a path from OpenEMR with the bearer token attached. Throws
 * FhirError on non-2xx responses with the status + parsed body.
 */
export async function fetchJson<T>(path: string, opts: FetchOptions = {}): Promise<T> {
  const token = getToken();
  if (!token) {
    throw new FhirError("No OpenEMR access token. Pass via ?access_token=...", 401);
  }
  const flavor = opts.flavor ?? "fhir";
  const prefix = flavor === "rest" ? "/apis/default/api" : "/apis/default/fhir";
  const url = `${BASE}${prefix}${path}`;

  const resp = await fetch(url, {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/fhir+json, application/json",
    },
    signal: opts.signal,
  });

  if (!resp.ok) {
    let body: unknown;
    try {
      body = await resp.json();
    } catch {
      body = await resp.text();
    }
    throw new FhirError(`${resp.status} ${resp.statusText}`, resp.status, body);
  }
  return resp.json() as Promise<T>;
}
