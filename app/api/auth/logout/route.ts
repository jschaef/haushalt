import { NextResponse, type NextRequest } from "next/server";
import { clearSession } from "@/lib/auth-route";
import { SESSION_COOKIE, apiUrl } from "@/lib/session";

// Revokes the token at the API and drops the cookie - the cookie goes in any
// case, also when the API is unreachable.
export async function POST(request: NextRequest) {
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  let revoked = false;
  if (token) {
    try {
      const upstream = await fetch(`${apiUrl()}/api/v1/logout`, {
        method: "POST",
        headers: { authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      revoked = upstream.ok;
    } catch {
      revoked = false;
    }
  }
  return clearSession(NextResponse.json({ ok: true, revoked }));
}
