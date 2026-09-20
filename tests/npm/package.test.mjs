import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import test from "node:test";

import { parseInvocation, runtimeDirectory } from "../../scripts/runtime.js";

const packageMetadata = JSON.parse(readFileSync("package.json", "utf8"));

execFileSync("npm", ["run", "build"], { stdio: "inherit" });
execFileSync("node", ["scripts/verify-package.js"], { stdio: "inherit" });

test("npm metadata exposes the Linux launcher", () => {
  assert.equal(packageMetadata.name, "@thegm26/agenthop");
  assert.equal(packageMetadata.os[0], "linux");
  assert.equal(packageMetadata.bin.agenthop, "bin/agenthop.js");
  assert.equal(packageMetadata.scripts.postinstall, undefined);
});

test("launcher routes desktop and API commands without install hooks", () => {
  assert.deepEqual(parseInvocation([]), { mode: "desktop", args: [] });
  assert.deepEqual(parseInvocation(["--port", "9123"]), {
    mode: "desktop",
    args: ["--port", "9123"],
  });
  assert.deepEqual(parseInvocation(["api", "--port", "8765"]), {
    mode: "api",
    args: ["--port", "8765"],
  });
  assert.equal(
    runtimeDirectory("0.2.0", { XDG_CACHE_HOME: "/tmp/agenthop-cache" }, "/home/test"),
    "/tmp/agenthop-cache/agenthop/0.2.0",
  );
});

test("npm tarball includes the desktop runtime and built dashboard", () => {
  const output = execFileSync("npm", ["pack", "--dry-run", "--json", "--ignore-scripts"], {
    encoding: "utf8",
  });
  const packedFiles = new Set(JSON.parse(output)[0].files.map((file) => file.path));
  for (const requiredFile of [
    "bin/agenthop.js",
    "backend/agenthop/desktop.py",
    "frontend/dist/index.html",
    "frontend/dist/assets/agenthop-mascot.png",
    "pyproject.toml",
    "scripts/runtime.js",
  ]) {
    assert.ok(packedFiles.has(requiredFile), `${requiredFile} must be published`);
  }
});
