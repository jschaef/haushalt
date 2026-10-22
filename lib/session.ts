// Server-only values shared by proxy.ts and the route handlers. The token
// lives in an httpOnly cookie and is never readable from browser JavaScript.

export const SESSION_COOKIE = "haushalt_session";
export const LOCALE_COOKIE = "haushalt_locale";

// haushalt-api (backend/). Read at request time, so one container image
// works with any API address.
export function apiUrl(): string {
  return (process.env.HAUSHALT_API_URL ?? "http://127.0.0.1:8300").replace(/\/$/, "");
}

// Secure cookies need HTTPS. Default: on in production builds, overridable
// for plain-HTTP setups with HAUSHALT_COOKIE_SECURE=false.
export function cookieSecure(): boolean {
  const flag = process.env.HAUSHALT_COOKIE_SECURE;
  if (flag !== undefined) return flag === "true" || flag === "1";
  return process.env.NODE_ENV === "production";
}
