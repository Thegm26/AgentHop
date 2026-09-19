import { existsSync, readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { homedir } from "node:os";
import { dirname, isAbsolute, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const systemPython = "/usr/bin/python3";

export function packageRoot() {
  return resolve(dirname(fileURLToPath(import.meta.url)), "..");
}

export function cacheRoot(environment = process.env, home = homedir()) {
  const configured = environment.XDG_CACHE_HOME;
  return configured && isAbsolute(configured) ? configured : join(home, ".cache");
}

export function runtimeDirectory(version, environment = process.env, home = homedir()) {
  return join(cacheRoot(environment, home), "agenthop", version);
}

export function parseInvocation(args) {
  if (args[0] === "api") {
    return { mode: "api", args: args.slice(1) };
  }
  if (args[0] === "desktop") {
    return { mode: "desktop", args: args.slice(1) };
  }
  return { mode: "desktop", args };
}

function commandWorks(command, args) {
  const result = spawnSync(command, args, { stdio: "ignore" });
  return !result.error && result.status === 0;
}

function fail(message) {
  console.error(message);
  return 1;
}

function printHelp() {
  console.log(`Usage: agenthop [desktop] [--port PORT]
       agenthop api [--host HOST] [--port PORT]

Start the AgentHop Linux system-tray application, or its loopback-only API.
The first run creates a private Python runtime in $XDG_CACHE_HOME/agenthop.

Requirements: Python 3.11+ with venv support, GTK 3, WebKit2GTK 4.1,
Ayatana AppIndicator3, and the Codex CLI on PATH.`);
}

function findPython(environment) {
  for (const candidate of [environment.PYTHON, "python3", "python"]) {
    if (
      candidate &&
      commandWorks(candidate, [
        "-c",
        "import sys; raise SystemExit(sys.version_info < (3, 11))",
      ])
    ) {
      return candidate;
    }
  }
  return null;
}

function ensureDesktopLibraries() {
  if (!existsSync(systemPython)) {
    return "AgentHop requires /usr/bin/python3 for the Linux desktop integration.";
  }
  const check = [
    "import gi",
    "gi.require_version('Gtk', '3.0')",
    "gi.require_version('WebKit2', '4.1')",
    "gi.require_version('AyatanaAppIndicator3', '0.1')",
    "from gi.repository import Gtk, WebKit2, AyatanaAppIndicator3",
  ].join("; ");
  if (!commandWorks(systemPython, ["-c", check])) {
    return "AgentHop requires GTK 3, WebKit2GTK 4.1, and Ayatana AppIndicator3. Install your distribution's GTK, WebKit2GTK, and AppIndicator GObject-introspection packages.";
  }
  return null;
}

function ensureRuntime(root, version, environment) {
  const runtime = runtimeDirectory(version, environment);
  const runtimePython = join(runtime, "bin", "python");
  if (!existsSync(runtimePython)) {
    const python = findPython(environment);
    if (!python) {
      return { error: "AgentHop requires Python 3.11 or newer. Install it, then run agenthop again." };
    }
    const created = spawnSync(python, ["-m", "venv", runtime], {
      cwd: root,
      stdio: "inherit",
    });
    if (created.error || created.status !== 0) {
      return {
        error: "AgentHop could not create its Python runtime. Install your distribution's Python venv package, then run agenthop again.",
      };
    }
  }
  if (!commandWorks(runtimePython, ["-c", "import agenthop"])) {
    if (!commandWorks(runtimePython, ["-m", "pip", "--version"])) {
      return {
        error: "AgentHop's Python runtime does not include pip. Install your distribution's Python ensurepip or venv package, then run agenthop again.",
      };
    }
    const installed = spawnSync(
      runtimePython,
      [
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-input",
        "--no-cache-dir",
        root,
      ],
      { cwd: root, stdio: "inherit" },
    );
    if (installed.error || installed.status !== 0) {
      return {
        error: "AgentHop could not install its Python dependencies. Check your network connection and pip configuration, then run agenthop again.",
      };
    }
  }
  return { runtimePython };
}

export function runLauncher(args, environment = process.env) {
  const root = packageRoot();
  const metadata = JSON.parse(readFileSync(join(root, "package.json"), "utf8"));
  if (args.includes("--help") || args.includes("-h")) {
    printHelp();
    return 0;
  }
  if (args.includes("--version") || args.includes("-v")) {
    console.log(metadata.version);
    return 0;
  }
  if (process.platform !== "linux") {
    return fail("AgentHop desktop mode currently supports Linux only.");
  }
  if (!commandWorks("codex", ["--version"])) {
    console.error(
      "Warning: Codex CLI was not found on PATH. Install Codex before adding or refreshing Codex accounts.",
    );
  }

  const invocation = parseInvocation(args);
  if (invocation.mode === "desktop") {
    const desktopError = ensureDesktopLibraries();
    if (desktopError) {
      return fail(desktopError);
    }
  }
  const runtime = ensureRuntime(root, metadata.version, environment);
  if (runtime.error) {
    return fail(runtime.error);
  }
  const pythonArguments =
    invocation.mode === "api"
      ? ["-m", "agenthop", ...invocation.args]
      : ["-m", "agenthop", "desktop", ...invocation.args];
  const child = spawnSync(runtime.runtimePython, pythonArguments, {
    cwd: root,
    env: {
      ...environment,
      AGENTHOP_PROJECT_ROOT: root,
      AGENTHOP_FRONTEND_DIST: join(root, "frontend", "dist"),
    },
    stdio: "inherit",
  });
  if (child.error) {
    return fail(`AgentHop could not start: ${child.error.message}`);
  }
  return child.status ?? 1;
}
