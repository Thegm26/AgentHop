#!/usr/bin/env node

import { runLauncher } from "../scripts/runtime.js";

process.exit(await runLauncher(["auto", "--", ...process.argv.slice(2)]));
