#!/usr/bin/env node

import { runLauncher } from "../scripts/runtime.js";

process.exit(runLauncher(process.argv.slice(2)));
