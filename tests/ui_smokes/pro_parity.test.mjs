#!/usr/bin/env node
/**
 * Pro-parity smoke tests — regression guards for the three bugs fixed by
 * copying Pro overlay.js + voices.js verbatim into free app.js.
 *
 * Bug 1: Language Remove/delete did NOT work in free.
 * Bug 2: Download progress bar was wrong/stuck.
 * Bug 3: Karaoke overlay was an empty black window.
 *
 * Run: node tests/ui_smokes/pro_parity.test.mjs
 */

import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const root = join(__dirname, '../..');

function read(rel) { return readFileSync(join(root, rel), 'utf8'); }

let passed = 0, failed = 0;
function assert(condition, label) {
  if (condition) { console.log(`PASS: ${label}`); passed++; }
  else           { console.error(`FAIL: ${label}`); failed++; }
}

const src        = read('webui/js/app.js');
const overlayCss = read('webui/css/overlay.css');
const themeCss   = read('webui/css/theme.css');

// (a) Regression guard: diag card still present
assert(/function buildDiagCard/.test(src),        '(a) buildDiagCard defined');
assert(src.includes('settings-diag-level'),        '(a) settings-diag-level present');
assert(/view\.appendChild\s*\(\s*buildDiagCard/.test(src), '(a) buildDiagCard wired in renderSettings');
assert(src.includes('"get_diag_state"'),           '(a) get_diag_state bridge call present');

// (b) Voice manager: Remove/delete uses Pro code path
assert(src.includes('function signalInstalledVoicesChanged'),
  '(b) signalInstalledVoicesChanged defined (inline from app-core.js)');
assert(src.includes('INSTALLED_VOICES_CHANGED_EVENT'),
  '(b) INSTALLED_VOICES_CHANGED_EVENT present');

const doRemoveIdx = src.indexOf('function doRemove');
const doInstallIdx = src.indexOf('function doInstall');
const doRemoveBlock = src.slice(doRemoveIdx, doInstallIdx);
assert(doRemoveBlock.includes('signalInstalledVoicesChanged'),
  '(b) doRemove() calls signalInstalledVoicesChanged — Remove wired');
assert(doRemoveBlock.includes('"get_voice_catalogue"'),
  '(b) doRemove() re-fetches catalogue');
assert(/testid.*vm-action-/.test(src),
  '(b) vm-action-{id} testid present (Remove/Install button)');
assert(src.includes('confirmDialog("Remove voice"'),
  '(b) Remove gated on confirmDialog (Pro pattern)');

// (c) Progress bar: correct Pro CSS classes
assert(src.includes('install-progress-wrap'),  '(c) install-progress-wrap in voiceRow JS');
assert(src.includes('install-progress-fill'),  '(c) install-progress-fill in voiceRow JS');
assert(src.includes('install-progress-bar'),   '(c) install-progress-bar in voiceRow JS');
assert(src.includes('vm-cancel-'),             '(c) voiceCancelBtn (vm-cancel-) present');
assert(themeCss.includes('.install-progress-fill'), '(c) .install-progress-fill CSS in theme.css');
assert(themeCss.includes('transition: width'), '(c) transition:width in theme.css');
assert(src.includes('vm-action-row'),          '(c) vm-action-row in voiceRow JS');
assert(themeCss.includes('.vm-action-row'),    '(c) .vm-action-row CSS in theme.css');

// (d) Overlay: position:fixed + Pro panel structure
assert(overlayCss.includes('position: fixed'),
  '(d) overlay-panel uses position:fixed (empty-black-window fix)');
assert(src.includes('testid: "overlay-panel"'),   '(d) overlay-panel element created');
assert(src.includes('testid: "overlay-loading"'), '(d) overlay-loading sentinel element');
assert(src.includes('testid: "overlay-page-marker"'), '(d) overlay-page-marker (counter)');
// Transport buttons are created via obtn("prev") etc. — testid is "overlay-" + tag
assert(src.includes('obtn("prev")'),  '(d) overlay-prev transport button (obtn call)');
assert(src.includes('obtn("next")'),  '(d) overlay-next transport button (obtn call)');
assert(src.includes('obtn("pause")'), '(d) overlay-pause transport button (obtn call)');
assert(src.includes('testid: "overlay-" + tag'),
  '(d) transport button testid pattern overlay-{tag} present');
assert(src.includes('TICK_FAST_MS'),  '(d) TICK_FAST_MS idle-aware polling');
assert(src.includes('TICK_SLOW_MS'),  '(d) TICK_SLOW_MS idle-aware polling');
assert(src.includes('reader-loading-bar'), '(d) reader-loading-bar in renderOverlay');
assert(overlayCss.includes('reader-loading-shimmer'), '(d) reader-loading-shimmer @keyframes');
assert(src.includes('window.__pippalOverlayKick'), '(d) window.__pippalOverlayKick exposed');

// (e) windows.py kick wired
let winPy = '';
try { winPy = read('src/pippal/web_ui/windows.py'); } catch(e) {}
assert(winPy.includes('__pippalOverlayKick'),
  '(e) windows.py evaluate_js kick wired after overlay show');

if (failed > 0) {
  console.error(`\n${failed} of ${passed + failed} test(s) FAILED.`);
  process.exit(1);
} else {
  console.log(`\nAll ${passed} tests passed.`);
  process.exit(0);
}
