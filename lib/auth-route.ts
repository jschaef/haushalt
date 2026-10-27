import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE, apiUrl, cookieSecure } from "@/lib/session";

// Shared by the login and signup route handlers (app/api/auth/*).

export type TokenResponse = {
  access_token: string;
  token_type: string;
  expires_at: number;
  must_change_password?: boolean;
  is_operator?: boolean;
};

// POSTs JSON to the API and turns a token answer into the session cookie.
// The token itself never reaches the browser's JavaScript.
export async function tokenRequest(path: string, body: unknown, bearer?: string): Promise<NextResponse> {
  let upstream: Response;
  try {
    upstream = await fetch(`${apiUrl()}/api/v1/${path}`, {
      method: "POST",
      headers: { "content-type": "application/json", ...(bearer ? { authorization: `Bearer ${bearer}` } : {}) },
      body: JSON.stringify(body),
      cache: "no-store",
    });
  } catch {
    return NextResponse.json({ detail: "API not reachable" }, { status: 502 });
  }
  const data = await upstream.json().catch(() => ({}));
  if (!upstream.ok) {
    return NextResponse.json({ detail: data.detail ?? "Request failed" }, { status: upstream.status });
  }
  const token = data as TokenResponse;
  return setSession(
    NextResponse.json({ ok: true, must_change_password: Boolean(token.must_change_password), is_operator: Boolean(token.is_operator) }),
    token,
  );
}

export function setSession(response: NextResponse, token: TokenResponse) {
  const maxAge = Math.max(0, token.expires_at - Math.floor(Date.now() / 1000));
  response.cookies.set(SESSION_COOKIE, token.access_token, {
    httpOnly: true,
    secure: cookieSecure(),
    sameSite: "lax",
    path: "/",
    maxAge,
  });
  return response;
}

export function clearSession(response: NextResponse) {
  response.cookies.set(SESSION_COOKIE, "", { httpOnly: true, secure: cookieSecure(), sameSite: "lax", path: "/", maxAge: 0 });
  return response;
}

// Changing requests must come from this site (CSRF, also login CSRF), in
// addition to the SameSite=Lax cookie. Browsers always send Origin on POST
// from fetch(). A reverse proxy has to pass the Host header with its port.
export function sameOrigin(request: NextRequest): boolean {
  const origin = request.headers.get("origin");
  if (!origin) return false;
  // Origins the app is reached at, e.g. behind `tailscale serve`
  // (HAUSHALT_PUBLIC_ORIGIN, comma-separated), are accepted as well.
  if (publicOrigins().includes(origin.replace(/\/$/, "").toLowerCase())) return true;
  const host = request.headers.get("x-forwarded-host") ?? request.headers.get("host");
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}

function publicOrigins(): string[] {
  return (process.env.HAUSHALT_PUBLIC_ORIGIN ?? "")
    .split(",")
    .map((value) => value.trim().replace(/\/$/, "").toLowerCase())
    .filter(Boolean);
}

export async function readJson(request: NextRequest): Promise<Record<string, unknown> | null> {
  try {
    const body = await request.json();
    return body && typeof body === "object" ? body : null;
  } catch {
    return null;
  }
}
