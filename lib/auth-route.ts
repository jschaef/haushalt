import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE, apiUrl, cookieSecure } from "@/lib/session";

// Shared by the login and signup route handlers (app/api/auth/*).

export type TokenResponse = { access_token: string; token_type: string; expires_at: number };

// POSTs JSON to the API and turns a token answer into the session cookie.
export async function tokenRequest(path: string, body: unknown): Promise<NextResponse> {
  let upstream: Response;
  try {
    upstream = await fetch(`${apiUrl()}/api/v1/${path}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
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
  return setSession(NextResponse.json({ ok: true }), data as TokenResponse);
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
  const host = request.headers.get("x-forwarded-host") ?? request.headers.get("host");
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}

export async function readJson(request: NextRequest): Promise<Record<string, unknown> | null> {
  try {
    const body = await request.json();
    return body && typeof body === "object" ? body : null;
  } catch {
    return null;
  }
}
