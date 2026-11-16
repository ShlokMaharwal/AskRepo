import { spawnSync } from "node:child_process";

// This only builds local Vercel output. It never invokes a deployment CLI.
const result = spawnSync(process.execPath, ["node_modules/vite/bin/vite.js", "build"], {
  stdio: "inherit",
  env: { ...process.env, NITRO_PRESET: "vercel" },
});
process.exit(result.status ?? 1);
