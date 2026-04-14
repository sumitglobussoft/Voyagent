/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The authenticated app is reverse-proxied at /app/* by the inner
  // nginx. Setting basePath makes Next.js emit every route AND every
  // static asset under /app/_next/* so it doesn't collide with the
  // marketing app's /_next/* assets. Server actions, <Link href>,
  // and redirect() take un-prefixed paths and the framework prepends
  // /app automatically; HTML form `action="..."` attrs are NOT
  // auto-prefixed so they must include /app explicitly.
  basePath: "/app",
};

export default nextConfig;
