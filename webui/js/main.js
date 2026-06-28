/* main.js — PipPal (free) web-UI module entrypoint.
 *
 * Loaded as <script type="module"> from index.html, AFTER the classic
 * api.js / pro_diag_instrument.js / pro_bridge_resilient.js / components.js
 * scripts (which set window.PipPalAPI / window.UI). This file is the
 * single module entry; it imports shared singletons + helpers from
 * app-core.js and the feature-surface renderers from their own modules,
 * then dispatches the ?view= surface.
 *
 * Surfaces in this build: overlay, voices, notices, onboarding.
 * Settings: temporary stub (settings-stub.js) until Step 5 ports the full
 *           settings surface from Pro. ?view=settings renders a placeholder.
 * Stripped (not in free): moods, release, import, queue, recent.
 *
 * Step-5 implementer: swap the settings-stub.js imports for the real
 *   import { renderSettings } from "./settings.js";
 *   import { wireFooter }     from "./settings-footer.js";
 * once those modules are ported. */
"use strict";

import { API, SURFACE, toast, fail } from "./app-core.js";
import { renderSettings, wireFooter } from "./settings-stub.js";
import { renderOnboarding } from "./onboarding.js";
import { renderVoiceManager } from "./voices.js";
import { renderNotices } from "./notices.js";
import { renderOverlay } from "./overlay.js";

// ------------------------------------------------------------------
// Boot
// ------------------------------------------------------------------
var renderers = {
  settings: renderSettings,
  onboarding: renderOnboarding,
  voices: renderVoiceManager,
  notices: renderNotices,
  overlay: renderOverlay,
};

// Wire footer buttons ONCE per document on the settings surface.
// wireFooter() uses addEventListener with NO removal; calling it more
// than once would double-bind Save/Apply (double-save bug). It is
// intentionally NOT called inside renderers.settings so __pippalRefresh
// can re-run renderSettings() to refresh data without re-wiring.
if (SURFACE === "settings" || !SURFACE) {
  wireFooter();
}

// __pippalRefresh: in-place data refresh hook called by Python on
// hide()->show() reopen (window_lifecycle.open via evaluate_js).
// Re-runs ONLY the data renderer (NOT wireFooter) to refresh DOM
// from get_config() / get_queue() / etc. and re-asserts data-ready.
// Guard (&&) makes it a no-op on surfaces that don't register it.
window.__pippalRefresh = function () {
  return (renderers[SURFACE] || renderers.settings)()
    .then(function () {
      document.body.setAttribute("data-ready", SURFACE);
    })
    .catch(fail);
};

(renderers[SURFACE] || renderers.settings)()
  .then(function () {
    document.body.setAttribute("data-ready", SURFACE);
  })
  .catch(fail);
