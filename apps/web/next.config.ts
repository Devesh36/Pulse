import type { NextConfig } from "next";
const siteOnly = process.env.PULSE_PUBLIC_SITE === "1";
const config: NextConfig = {
  output: "standalone",
  ...(siteOnly ? { pageExtensions: ["site.tsx"] } : {}),
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "same-origin" },
          {
            key: "Content-Security-Policy",
            value:
              "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'",
          },
        ],
      },
    ];
  },
};
export default config;
