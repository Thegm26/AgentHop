import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { parseInvocation, runtimeDirectory } from "../../scripts/runtime.js";

const packageMetadata = JSON.parse(readFileSync("package.json", "utf8"));

execFileSync("npm", ["run", "build"], { stdio: "inherit" });
execFileSync("node", ["scripts/verify-package.js"], { stdio: "inherit" });

test("npm metadata exposes the Linux launcher", () => {
  assert.equal(packageMetadata.name, "@thegm26/agenthop");
  assert.equal(packageMetadata.os[0], "linux");
  assert.equal(packageMetadata.bin.agenthop, "bin/agenthop.js");
  assert.equal(packageMetadata.bin["codex-auto"], "bin/codex-auto.js");
  assert.equal(packageMetadata.scripts.postinstall, undefined);
});

test("launcher routes desktop, API, and headless auto commands without install hooks", () => {
  assert.deepEqual(parseInvocation([]), { mode: "desktop", args: [] });
  assert.deepEqual(parseInvocation(["--port", "9123"]), {
    mode: "desktop",
    args: ["--port", "9123"],
  });
  assert.deepEqual(parseInvocation(["api", "--port", "8765"]), {
    mode: "api",
    args: ["--port", "8765"],
  });
  assert.deepEqual(parseInvocation(["auto", "--", "resume", "thread-1"]), {
    mode: "auto",
    args: ["--", "resume", "thread-1"],
  });
  assert.equal(
    runtimeDirectory("0.2.1", { XDG_CACHE_HOME: "/tmp/agenthop-cache" }, "/home/test"),
    "/tmp/agenthop-cache/agenthop/0.2.1",
  );
});

test("top-level help documents polling without automatic review messages", () => {
  const output = execFileSync("node", ["bin/agenthop.js", "--help"], { encoding: "utf8" });
  assert.match(output, /--poll-interval SECONDS/);
  assert.doesNotMatch(output, /review-drain/);
});

test("codex-auto forwards literal Codex arguments and the supervisor exit status", () => {
  const directory = mkdtempSync(join(tmpdir(), "agenthop-launcher-"));
  try {
    const commands = join(directory, "commands");
    const pythonDirectory = join(runtimeDirectory(packageMetadata.version, {
      XDG_CACHE_HOME: directory,
    }), "bin");
    mkdirSync(commands, { recursive: true });
    mkdirSync(pythonDirectory, { recursive: true });
    writeFileSync(join(commands, "codex"), "#!/bin/sh\nexit 0\n", { mode: 0o755 });
    const captured = join(directory, "arguments.json");
    writeFileSync(join(pythonDirectory, "python"), `#!${process.execPath}
const fs = require("node:fs");
const args = process.argv.slice(2);
if (args[0] === "-c") process.exit(0);
fs.writeFileSync(process.env.AGENTHOP_TEST_ARGUMENTS, JSON.stringify(args));
process.exit(37);
`, { mode: 0o755 });
    for (const args of [
      [],
      ["resume"],
      ["resume", "session with spaces", "--last"],
      ["a prompt with 'quotes', $variables, and ; punctuation", "--model", "example"],
      ["--help"],
      ["--version"],
      ["-h", "-v", "--", ""],
    ]) {
      const result = spawnSync(process.execPath, ["bin/codex-auto.js", ...args], {
        encoding: "utf8",
        env: {
          ...process.env,
          PATH: `${commands}:${process.env.PATH}`,
          XDG_CACHE_HOME: directory,
          AGENTHOP_TEST_ARGUMENTS: captured,
        },
      });
      assert.ifError(result.error);
      assert.equal(result.status, 37, result.stderr || result.stdout);
      assert.deepEqual(JSON.parse(readFileSync(captured, "utf8")), [
        "-m", "agenthop", "auto", "--", ...args,
      ]);
    }
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("npm tarball includes the desktop runtime and built dashboard", () => {
  const output = execFileSync("npm", ["pack", "--dry-run", "--json", "--ignore-scripts"], {
    encoding: "utf8",
  });
  const packedFiles = new Set(JSON.parse(output)[0].files.map((file) => file.path));
  for (const requiredFile of [
    "bin/agenthop.js",
    "bin/codex-auto.js",
    "backend/agenthop/desktop.py",
    "frontend/dist/index.html",
    "frontend/dist/assets/agenthop-mascot.png",
    "pyproject.toml",
    "scripts/runtime.js",
  ]) {
    assert.ok(packedFiles.has(requiredFile), `${requiredFile} must be published`);
  }
});
