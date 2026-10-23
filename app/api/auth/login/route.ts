import { NextResponse, type NextRequest } from "next/server";
import { readJson, sameOrigin, tokenRequest } from "@/lib/auth-route";

export async function POST(request: NextRequest) {
  if (!sameOrigin(request)) return NextResponse.json({ detail: "Cross-site login rejected" }, { status: 403 });
  const body = await readJson(request);
  if (!body) return NextResponse.json({ detail: "Invalid request" }, { status: 400 });
  return tokenRequest("token", { username: String(body.username ?? "").trim(), password: String(body.password ?? "") });
}
