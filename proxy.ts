import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE } from "@/lib/session";

// Pages: optimistic check only. The API validates the token on every call;
// an expired token makes the client log out (see lib/api.ts).
export function proxy(request: NextRequest) {
  if (!request.cookies.get(SESSION_COOKIE)) {
    const login = new URL("/login", request.url);
    login.searchParams.set("next", request.nextUrl.pathname + request.nextUrl.search);
    return NextResponse.redirect(login);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/password", "/operator/:path*", "/dashboard/:path*", "/receipts/:path*", "/fixed/:path*", "/utilities/:path*", "/bank/:path*", "/settings/:path*"],
};
