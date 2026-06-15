/**
 * Next.js is the single public front door (Railway $PORT). It reverse-proxies
 * API + Django admin/static to the Django process running inside the same
 * service via rewrites. Server Components call Django directly (BACKEND_INTERNAL_URL).
 */
const backend = process.env.BACKEND_INTERNAL_URL || "http://127.0.0.1:8000";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Self-contained server bundle for the single-container Railway deploy.
  output: "standalone",
  // Don't redirect away trailing slashes; pages stay slash-less. Django routes
  // need the slash, so we append it in the rewrite destinations below — the
  // `:path*` matcher drops the trailing slash, so we add it back explicitly.
  skipTrailingSlashRedirect: true,
  // Lint is run separately in CI; don't fail production builds on it.
  eslint: { ignoreDuringBuilds: true },
  async rewrites() {
    return [
      // API + admin require a trailing slash (Django APPEND_SLASH).
      { source: "/api/:path*", destination: `${backend}/api/:path*/` },
      { source: "/admin", destination: `${backend}/admin/` },
      { source: "/admin/:path*", destination: `${backend}/admin/:path*/` },
      // Django static (admin/DRF assets) are files — no trailing slash.
      { source: "/static/:path*", destination: `${backend}/static/:path*` },
      { source: "/healthz", destination: `${backend}/healthz` },
    ];
  },
};

export default nextConfig;
