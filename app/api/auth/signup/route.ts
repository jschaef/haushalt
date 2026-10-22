import { NextResponse, type NextRequest } from "next/server";
import { readJson, sameOrigin, tokenRequest } from "@/lib/auth-route";

// Creates the first household member (the API refuses once one exists,
// unless HAUSHALT_ALLOW_SIGNUP is set) and logs them in.
export async function POST(request: NextRequest) {
  if (!sameOrigin(request)) return NextResponse.json({ detail: "Cross-site signup rejected" }, { status: 403 });
  const body = await readJson(request);
  if (!body) return NextResponse.json({ detail: "Invalid request" }, { status: 400 });
  return tokenRequest("signup", {
    username: String(body.username ?? "").trim(),
    password: String(body.password ?? ""),
    display_name: String(body.display_name ?? "").trim(),
  });
}
