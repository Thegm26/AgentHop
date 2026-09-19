import { existsSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(fileURLToPath(new URL("..", import.meta.url)));
const metadata = JSON.parse(readFileSync(join(root, "package.json"), "utf8"));
const requiredFiles = [
  "bin/agenthop.js",
  "backend/agenthop/desktop.py",
  "frontend/dist/index.html",
  "frontend/dist/assets/agenthop-mascot.png",
  "pyproject.toml",
  "scripts/runtime.js",
];
const failures = requiredFiles
  .filter((path) => !existsSync(join(root, path)))
  .map((path) => `missing required package file: ${path}`);

if (metadata.name !== "agenthop") {
  failures.push("package name must be agenthop");
}
if (metadata.bin?.agenthop !== "./bin/agenthop.js") {
  failures.push("package must expose the agenthop launcher");
}
if (!metadata.os?.includes("linux")) {
  failures.push("package must be restricted to Linux");
}
if (metadata.scripts?.postinstall) {
  failures.push("package must not use a postinstall hook");
}

if (failures.length) {
  console.error(`AgentHop package verification failed:\n${failures.join("\n")}`);
  process.exit(1);
}
