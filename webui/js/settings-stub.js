/* settings-stub.js — temporary settings surface placeholder.
 *
 * Used by main.js until Step 5 (the full settings port) is implemented.
 * Renders a minimal placeholder card so ?view=settings does not hard-crash.
 * The existing settings logic remains in app.js (not loaded by index.html)
 * and will be migrated by the Step-5 implementer into settings.js /
 * settings-cards.js / settings-footer.js at that point.
 *
 * Step-5 implementer: replace this file with the real settings.js and
 * update main.js to import renderSettings from "./settings.js" instead
 * of "./settings-stub.js".  Also replace wireFooter import to come from
 * "./settings-footer.js". */
"use strict";

import { U, API, view, footer, fail } from "./app-core.js";

export function renderSettings() {
  // Delegate to the legacy app.js IIFE if it registered itself.
  // app.js is NOT loaded by index.html in the new ES6-module build, so
  // this branch is only for future compatibility or manual testing where
  // app.js is still injected.  In normal operation the placeholder below runs.
  if (window.__pippalLegacyRenderSettings) {
    return window.__pippalLegacyRenderSettings();
  }
  view.innerHTML = "";
  footer.classList.add("hidden");
  view.appendChild(
    U.card("Settings", [
      U.hint("Settings are being migrated (Step 5). Use the system tray to access settings for now."),
    ]),
  );
  return Promise.resolve();
}

export function wireFooter() {
  // No-op placeholder — the real wireFooter in settings-footer.js wires
  // Save / Apply / Cancel / Reset buttons once the settings surface is ported.
  // Until then the footer stays hidden (renderSettings above does not show it).
}
