import { spawn } from "node:child_process";

const command = process.argv[2];
if (!["build", "dev"].includes(command)) {
  throw new Error("Use site.mjs build or site.mjs dev.");
}
const child = spawn(
  process.execPath,
  ["node_modules/next/dist/bin/next", command, ...process.argv.slice(3)],
  {
    stdio: "inherit",
    env: { ...process.env, PULSE_PUBLIC_SITE: "1" },
  },
);
for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => child.kill(signal));
}
child.on("error", (error) => {
  console.error(error.message);
  process.exitCode = 1;
});
child.on("exit", (code, signal) => {
  process.exitCode = code ?? (signal ? 1 : 0);
});
