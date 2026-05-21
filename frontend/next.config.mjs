/** @type {import('next').NextConfig} */
const nextConfig = {
  // In development (no NEXT_PUBLIC_API_URL), proxy /api/* → localhost:8000
  // In production (Vercel), NEXT_PUBLIC_API_URL is set and the frontend calls
  // the Render backend directly — no proxy needed.
  ...(!process.env.NEXT_PUBLIC_API_URL && {
    async rewrites() {
      return [
        {
          source: "/api/:path*",
          destination: "http://localhost:8000/:path*",
        },
      ];
    },
  }),
};

export default nextConfig;
