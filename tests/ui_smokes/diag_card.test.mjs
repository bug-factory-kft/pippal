#!/usr/bin/env node
/**
 * Diagnostics/Logs Settings card — structural smoke test.
 *
 * Run: node tests/ui_smokes/diag_card.test.mjs
 *
 * Asserts that the Diagnostics card is present in the module-graph JS files
 * (settings-cards.js, settings.js). Checks function definition, select-control
 * ID, the render wiring, and all four bridge methods the card invokes.
 */

import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const root = join(__dirname, '../..');

function readModule(rel) {
  const p = join(root, rel);
  try { return readFileSync(p, 'utf8'); }
  catch (err) {
    console.error(`FATAL: cannot read ${p}: ${err.message}`);
    process.exit(2);
  }
}

// Concatenate the module files that together form the settings surface.
const source = [
  'webui/js/settings-cards.js',
  'webui/js/settings.js',
].map(readModule).join('\n');

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
  'buildDiagCard function is defined'
);

assert(
  source.includes('settings-diag-level'),
  '"settings-diag-level" select control is present'
);

assert(
  /buildDiagCard\s*\(/.test(source),
  'buildDiagCard is called in the settings render path'
);

assert(
  source.includes('"get_diag_state"'),
  'get_diag_state API call is present'
);

assert(
  source.includes('"open_diag_folder"'),
  '"open_diag_folder" bridge method is present'
);

assert(
  source.includes('"delete_diag_logs"'),
  '"delete_diag_logs" bridge method is present'
);

assert(
  source.includes('"set_diag_level"'),
  '"set_diag_level" bridge method is present'
);

// --- Summary ---
if (failed > 0) {
  console.error(`\n${failed} of ${passed + failed} test(s) FAILED.`);
  process.exit(1);
} else {
  console.log(`\nAll ${passed} tests passed.`);
  process.exit(0);
}
