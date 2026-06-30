/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Emit a self-contained server bundle (.next/standalone) so the Docker image
  // ships only what it needs — no full node_modules in the runtime stage.
  output: "standalone",
};

export default nextConfig;
