#!/usr/bin/env node
/**
 * Diagnostics/Logs Settings card — structural smoke test.
 *
 * Run: node tests/ui_smokes/diag_card.test.mjs
 *
 * Asserts that webui/js/app.js contains the Diagnostics card that was
 * accidentally dropped when the branch diverged from the commit that
 * introduced it (18bc0f8). This test FAILS when the card is absent and
 * PASSES after it is restored.
 *
 * A structural source-text check is used (rather than a full jsdom render)
 * because the IIFE in app.js requires mocking window.UI, window.PipPalAPI,
 * and a full DOM skeleton, which would cost more than the signal is worth.
 * The check is tight enough to catch the regression: it verifies the
 * function definition, the select-control ID, the view.appendChild call,
 * and the four bridge methods the card invokes.
 */

import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Resolve path relative to the repo root (two levels up from tests/ui_smokes/)
const appJsPath = join(__dirname, '../../webui/js/app.js');

let source;
try {
  source = readFileSync(appJsPath, 'utf8');
} catch (err) {
  console.error(`FATAL: cannot read ${appJsPath}: ${err.message}`);
  process.exit(2);
}

let passed = 0;
let failed = 0;

function assert(condition, label) {
  if (condition) {
    console.log(`PASS: ${label}`);
    passed++;
  } else {
    console.error(`FAIL: ${label}`);
    failed++;
  }
}

// --- Tests ---

assert(
  /function buildDiagCard/.test(source),
  'buildDiagCard function is defined in app.js'
);

assert(
  source.includes('settings-diag-level'),
  '"settings-diag-level" select control is present in app.js'
);

assert(
  /view\.appendChild\s*\(\s*buildDiagCard/.test(source),
  'buildDiagCard is called via view.appendChild in the settings render path'
);

assert(
  source.includes('"get_diag_state"'),
  'get_diag_state API call is present in app.js'
);

assert(
  source.includes('"open_diag_folder"'),
  '"open_diag_folder" bridge method is present in app.js'
);

assert(
  source.includes('"delete_diag_logs"'),
  '"delete_diag_logs" bridge method is present in app.js'
);

assert(
  source.includes('"set_diag_level"'),
  '"set_diag_level" bridge method is present in app.js'
);

// --- Summary ---
if (failed > 0) {
  console.error(`\n${failed} of ${passed + failed} test(s) FAILED.`);
  process.exit(1);
} else {
  console.log(`\nAll ${passed} tests passed.`);
  process.exit(0);
}
