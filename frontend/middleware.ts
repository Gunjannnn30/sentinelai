import { NextResponse, type NextRequest } from "next/server";

// Same-origin proxy: the browser talks only to this Next server, and the
// Next server forwards /api, /health, /ready and /metrics to the backend.
//
// Why proxy instead of calling the API from the page: the API is a different
// origin, so a direct browser call is cross-origin. The backend ships no CORS
// middleware by design, so those calls would be blocked. Proxying keeps the
// session + CSRF cookies first-party (no SameSite/Secure cross-site problems)
// and widens no attack surface. The backend still enforces CSRF, body-size and
// auth server-side.
//
// Why middleware and NOT next.config.ts `rewrites()`:
//   `rewrites()` is invoked once, by `next build`, and its result is frozen
//   into `.next/routes-manifest.json`. Anything it computes from process.env
//   is therefore a BUILD-time value. In Docker the build stage has no
//   SENTINEL_API_ORIGIN, so it silently baked `http://127.0.0.1:8123` and every
//   proxied path 500'd (connection refused to localhost inside the container),
//   even though the runner stage set the variable correctly at runtime.
// Middleware runs per request in the serving process, so `process.env` is read
// when it actually matters -- and this target can be changed without a rebuild.
const API_TARGET = (process.env.SENTINEL_API_ORIGIN ?? "http://127.0.0.1:8123").replace(/\/+$/, "");

export function middleware(request: NextRequest) {
  const destination = new URL(`${API_TARGET}${request.nextUrl.pathname}${request.nextUrl.search}`);
  // Forward the original headers unchanged: cookies, X-CSRF-Token, auth and
  // content-type must survive the hop or login and unsafe methods break.
  return NextResponse.rewrite(destination, { request: { headers: request.headers } });
}

// Kept in sync with the four paths the docs promise are proxied. Static assets,
// app routes and /_next/* are deliberately excluded.
export const config = {
  matcher: ["/api/:path*", "/health", "/ready", "/metrics"],
};
