import { cpSync, existsSync } from "node:fs";

const server = new URL("../.next/standalone/server.js", import.meta.url);
if (!existsSync(server)) {
  console.error("Run npm run build before starting Pulse web.");
  process.exit(1);
}
cpSync(
  new URL("../.next/static", import.meta.url),
  new URL("../.next/standalone/.next/static", import.meta.url),
  { recursive: true },
);
// Standalone output requires public assets alongside server.js.
const publicAssets = new URL("../public", import.meta.url);
if (existsSync(publicAssets)) {
  cpSync(publicAssets, new URL("../.next/standalone/public", import.meta.url), {
    recursive: true,
  });
}
// Next standalone reads HOSTNAME; keep native administrative access on loopback.
process.env.HOSTNAME = process.env.PULSE_WEB_HOST || "127.0.0.1";
process.env.PORT = process.env.PORT || "3000";
await import(server.href);
