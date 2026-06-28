/* settings-cards.js — Settings card builders. Free build: Piper voices only.
 * Only export: buildDiagCard. */
"use strict";

import { U, API, toast, fail, confirmDialog } from "./app-core.js";

// ------------------------------------------------------------------
// Diagnostics card (local logs only — no upload path).
// ------------------------------------------------------------------
export function buildDiagCard(state) {
  state = state || {};

  // 1. Log-level select: Off / Errors only / Full trace -> set_diag_level.
  var levelSel = U.select("settings-diag-level", [
    { value: "off",   label: "Off" },
    { value: "error", label: "Errors only" },
    { value: "trace", label: "Full trace" },
  ], state.level || "off");
  levelSel.classList.add("grow");

  // 2. Privacy description — no upload path.
  var noticeEl = U.el("div", {
    class: "card-hint",
    testid: "settings-diag-notice",
    html:
      "Diagnostics logs help the creator fix bugs. "
      + "<strong>Your reading text is never logged</strong> — only "
      + "technical metadata (sizes, formats, timings, and error types). "
      + "Logs stay on your computer. "
      + "Off keeps logging disabled; Errors only records failures; "
      + "Full trace records detailed step-by-step events for harder bugs.",
  });

  // 3. Status line: log count / KB / folder path -> get_diag_state.
  function statusText(s) {
    var kb = Math.round((s.total_bytes || 0) / 1024);
    return (s.log_count || 0) + " log file" + (s.log_count === 1 ? "" : "s")
      + "  \xb7  " + kb + " KB"
      + "  \xb7  " + (s.folder || "local PipPal folder");
  }
  var statusEl = U.el("div", {
    class: "card-hint",
    testid: "settings-diag-status",
    text: statusText(state),
  });

  function refreshStatus() {
    API.call("get_diag_state").then(function (s) {
      statusEl.textContent = statusText(s);
      levelSel.value = s.level || "off";
    }).catch(function () {});
  }

  // 4. Buttons: Open log folder + Delete logs (danger).
  var openBtn = U.el("button", {
    testid: "settings-diag-open",
    text: "Open log folder",
  });
  var deleteBtn = U.el("button", {
    class: "danger",
    testid: "settings-diag-delete",
    text: "Delete logs",
  });

  levelSel.addEventListener("change", function () {
    var lvl = levelSel.value;
    API.call("set_diag_level", lvl).then(function (r) {
      if (r && r.ok) {
        toast("Diagnostics level set to “" + lvl + "”.");
        refreshStatus();
      } else {
        fail(new Error(r && r.error ? r.error : "Failed to set level."));
      }
    }).catch(fail);
  });

  openBtn.addEventListener("click", function () {
    API.call("open_diag_folder").then(function (r) {
      if (r && !r.handled && state.folder) toast("Log folder: " + state.folder);
    }).catch(fail);
  });

  deleteBtn.addEventListener("click", function () {
    confirmDialog(
      "Delete diagnostics logs",
      "Delete all diagnostics logs? This cannot be undone.",
    ).then(function (ok) {
      if (!ok) return;
      API.call("delete_diag_logs").then(function (r) {
        if (r && r.ok) {
          toast("Deleted " + (r.removed || 0) + " log file"
            + (r.removed === 1 ? "" : "s") + ".");
        } else {
          fail(new Error(r && r.error ? r.error : "Delete failed."));
        }
        refreshStatus();
      }).catch(fail);
    });
  });

  return U.card("Diagnostics", [
    U.fieldRow("Log level", levelSel),
    noticeEl,
    statusEl,
    U.el("div", { class: "row", style: "margin-top:8px" }, [openBtn, deleteBtn]),
  ]);
}
