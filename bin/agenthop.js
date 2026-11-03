#!/usr/bin/env node

import { runLauncher } from "../scripts/runtime.js";

process.exit(await runLauncher(process.argv.slice(2)));
