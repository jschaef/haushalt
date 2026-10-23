import { NextResponse, type NextRequest } from "next/server";
import { sameOrigin } from "@/lib/auth-route";
import { SESSION_COOKIE, apiUrl } from "@/lib/session";

// Same-origin gateway to haushalt-api: adds the bearer token from the
// httpOnly cookie and streams bodies both ways (receipt uploads, images).
// A route handler instead of a rewrite: the API address is read at request
// time, and the 10 MB body limit of proxy.ts does not apply here.

const PUBLIC = new Set(["health", "setup"]);
const FORWARDED_REQUEST_HEADERS = ["content-type", "accept", "if-none-match"];
const FORWARDED_RESPONSE_HEADERS = ["content-type", "cache-control", "etag", "content-length"];

const SAFE_SEGMENT = /^[A-Za-z0-9_-]+$/;
// Meter devices push readings with their own device token instead of a
// browser session: no cookie, no Origin. Only this path and method pass the
// client's Authorization header on; a session token is never added to it.
const DEVICE_INGEST = "ingest/reading";
const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

async function forward(request: NextRequest, { params }: RouteContext<"/api/v1/[...path]">) {
  const { path } = await params;
  // only plain segments: no "..", no encoded slashes, nothing outside /api/v1
  if (!path.every((segment) => SAFE_SEGMENT.test(segment))) {
    return NextResponse.json({ detail: "Invalid path" }, { status: 400 });
  }
  const joined = path.join("/");
  const device = joined === DEVICE_INGEST;
  if (device && request.method !== "POST") {
    return NextResponse.json({ detail: "Method not allowed" }, { status: 405 });
  }
  if (!device && UNSAFE_METHODS.has(request.method) && !sameOrigin(request)) {
    return NextResponse.json({ detail: "Cross-site request rejected" }, { status: 403 });
  }
  const token = device ? undefined : request.cookies.get(SESSION_COOKIE)?.value;
  if (!token && !device && !PUBLIC.has(joined)) {
    return NextResponse.json({ detail: "Not logged in" }, { status: 401 });
  }
  const headers = new Headers();
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  if (token) headers.set("authorization", `Bearer ${token}`);
  if (device) {
    const deviceAuth = request.headers.get("authorization");
    if (!deviceAuth) return NextResponse.json({ detail: "Device token required" }, { status: 401 });
    headers.set("authorization", deviceAuth);
  }

  const hasBody = !["GET", "HEAD"].includes(request.method) && request.body;
  let upstream: Response;
  try {
    upstream = await fetch(`${apiUrl()}/api/v1/${joined}${request.nextUrl.search}`, {
      method: request.method,
      headers,
      body: hasBody ? request.body : undefined,
      // required by undici for streamed request bodies
      ...(hasBody ? { duplex: "half" } : {}),
      cache: "no-store",
    } as RequestInit & { duplex?: "half" });
  } catch {
    return NextResponse.json({ detail: "API not reachable" }, { status: 502 });
  }
  const responseHeaders = new Headers();
  for (const name of FORWARDED_RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }
  const body = upstream.status === 204 ? null : upstream.body;
  return new NextResponse(body, { status: upstream.status, headers: responseHeaders });
}

export { forward as GET, forward as POST, forward as PUT, forward as PATCH, forward as DELETE };
