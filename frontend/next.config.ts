import type { NextConfig } from "next";

// The same-origin proxy (browser -> this Next server -> backend) lives in
// `middleware.ts`, NOT in `rewrites()` here.
//
// `rewrites()` runs once during `next build` and its output is frozen into
// `.next/routes-manifest.json`, so any `process.env.SENTINEL_API_ORIGIN` read
// from it is a build-time value. Deploying with that approach silently baked
// the `http://127.0.0.1:8123` fallback into the image (the Docker build stage
// never has the variable) and every proxied path returned 500 at runtime.
// middleware.ts reads the same variable per request instead.
const nextConfig: NextConfig = {};

export default nextConfig;
