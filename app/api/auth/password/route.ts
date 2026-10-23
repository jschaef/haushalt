import { NextResponse, type NextRequest } from "next/server";
import { readJson, sameOrigin, tokenRequest } from "@/lib/auth-route";
import { SESSION_COOKIE } from "@/lib/session";

// Changes the own password (also the way out of a one-time password). The API
// ends all sessions of the account and returns a new token for this one.
export async function POST(request: NextRequest) {
  if (!sameOrigin(request)) return NextResponse.json({ detail: "Cross-site request rejected" }, { status: 403 });
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (!token) return NextResponse.json({ detail: "Not logged in" }, { status: 401 });
  const body = await readJson(request);
  if (!body) return NextResponse.json({ detail: "Invalid request" }, { status: 400 });
  return tokenRequest(
    "me/password",
    { current_password: String(body.current_password ?? ""), new_password: String(body.new_password ?? "") },
    token,
  );
}
