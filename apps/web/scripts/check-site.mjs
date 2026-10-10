import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const manifest = JSON.parse(
  await readFile(
    new URL("../.next/server/app-paths-manifest.json", import.meta.url),
  ),
);
const publicPages = Object.keys(manifest).filter(
  (path) => !["/_not-found/page", "/_global-error/page"].includes(path),
);
assert.deepEqual(publicPages.sort(), ["/docs/page", "/page"]);
console.log("PASS: public build contains only the landing page and Docs.");

const base = process.argv[2];
if (base) {
  for (const path of ["/", "/docs"]) {
    const response = await fetch(new URL(path, base));
    assert.equal(response.status, 200, path);
    const html = await response.text();
    assert.match(html, /Install Pulse/);
    assert.doesNotMatch(html, /href="\/dashboard"/);
    assert.match(html, /\/screenshots\/overview\.png/);
  }
  for (const path of [
    "/dashboard",
    "/lab",
    "/services",
    "/incidents",
    "/assistant",
    "/settings",
    "/api/v1/health",
    "/api/schema",
  ]) {
    const response = await fetch(new URL(path, base));
    assert.equal(response.status, 404, path);
  }
  for (const name of ["overview", "investigation", "verification"]) {
    const response = await fetch(new URL(`/screenshots/${name}.png`, base));
    assert.equal(response.status, 200, name);
    assert.equal(response.headers.get("content-type"), "image/png");
    const bytes = new Uint8Array(await response.arrayBuffer());
    assert.deepEqual([...bytes.slice(0, 8)], [137, 80, 78, 71, 13, 10, 26, 10]);
  }
  console.log(
    "PASS: landing, Docs and screenshots load; operational routes return 404.",
  );
}
