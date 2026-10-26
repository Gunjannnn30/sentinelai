import type { NextConfig } from "next";

// Same-origin proxy: the browser talks only to this Next server, and the
// Next server forwards /api, /health, /ready and /metrics to the backend.
//
// Why proxy instead of calling http://127.0.0.1:8123 directly from the page:
// the API is a different origin (port 3000 -> 8123), so a direct browser call
// is cross-origin. The backend ships no CORS middleware by design, so those
// calls would be blocked. Proxying keeps the session + CSRF cookies
// first-party (no SameSite/Secure cross-site problems) and widens no attack
// surface. The backend still enforces CSRF, body-size and auth server-side.
const API_TARGET = process.env.SENTINEL_API_ORIGIN ?? "http://127.0.0.1:8123";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      // Order matters: more specific paths first.
      { source: "/health", destination: `${API_TARGET}/health` },
      { source: "/ready", destination: `${API_TARGET}/ready` },
      { source: "/metrics", destination: `${API_TARGET}/metrics` },
      { source: "/api/:path*", destination: `${API_TARGET}/api/:path*` },
    ];
  },
};

export default nextConfig;
