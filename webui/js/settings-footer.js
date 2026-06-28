/* settings-footer.js — Settings surface glue: context-menu status helper,
 * read-back of control values, persist (Save/Apply), and footer button
 * wiring (Save / Apply / Cancel / Reset).
 *
 * Ported from Pro's settings-footer.js with paid fields stripped:
 *   - ollama_endpoint / ollama_allow_remote / ollama_model /
 *     ai_translate_target removed (no AI card in free)
 *   - Kokoro voice branch removed from collectSettingsValues (no Kokoro)
 *   - cleanup_* loop removed (no Cleanup card in free)
 *   - kokoro_lang skip removed from reset loop (no Kokoro) */
"use strict";

import {
  U,
  API,
  toast,
  fail,
  handleCloseWindowFailure,
  confirmDialog,
  settingsState,
} from "./app-core.js";
import {
  renderSettings,
  speedToLengthScale,
  lengthScaleToSpeed,
} from "./settings.js";

export function ctxText(status) {
  if (status === "all")
    return "✓ Right-click entry installed for .txt and .md.";
  if (status === "partial")
    return "⚠ Partial install — re-run Install to fix.";
  return "○ Right-click entry not installed.";
}

export function collectSettingsValues() {
  var c = settingsState.controls;
  var values = {
    engine: c.engine.value,
    length_scale: speedToLengthScale(parseFloat(c.speed.value)),
    noise_scale: parseFloat(c.noise_scale.value),
    show_overlay: c.show_overlay.checked,
    show_text_in_overlay: c.show_text_in_overlay.checked,
    auto_hide_ms: parseInt(c.auto_hide_ms.value, 10),
    overlay_y_offset: parseInt(c.overlay_y_offset.value, 10),
    karaoke_offset_ms: parseInt(c.karaoke_offset_ms.value, 10),
  };
  // Voice: plain Piper engine only (no Kokoro branch in free).
  if (c.voice && c.voice.value) values.voice = c.voice.value;
  Object.keys(c).forEach(function (k) {
    if (k.indexOf("hotkey_") === 0)
      values[k] = (c[k].value || "").trim().toLowerCase();
  });
  return values;
}

export function persist(close) {
  return API.call("save_config", collectSettingsValues(), close)
    .then(function (r) {
      if (r && r.hotkey_failures && r.hotkey_failures.length) {
        toast("Saved, but some hotkeys could not be bound.", true);
      } else {
        toast(close ? "Saved." : "Applied.");
      }
      if (close) {
        return API.call("close_window").catch(function (e) {
          return handleCloseWindowFailure(
            "Could not close settings window after save.",
            e,
            renderSettings,
          );
        });
      }
      return renderSettings();
    })
    .catch(fail);
}

export function wireFooter() {
  document.getElementById("btn-save").addEventListener("click", function () {
    persist(true);
  });
  document.getElementById("btn-apply").addEventListener("click", function () {
    persist(false);
  });
  document
    .getElementById("btn-cancel")
    .addEventListener("click", function () {
      API.call("close_window").catch(function (e) {
        return handleCloseWindowFailure(
          "Could not close settings window.",
          e,
          renderSettings,
        );
      });
    });
  document.getElementById("btn-reset").addEventListener("click", function () {
    confirmDialog(
      "Reset to defaults",
      "Reset every field to its built-in default? " +
        "Click Apply or Save afterwards to keep them.",
    ).then(function (ok) {
      if (!ok) return;
      var d = settingsState.defaults,
        c = settingsState.controls;
      if (d.length_scale != null && c.speed)
        c.speed.value = lengthScaleToSpeed(parseFloat(d.length_scale));
      Object.keys(c).forEach(function (k) {
        // Skip controls whose default is not relevant or managed elsewhere.
        if (k === "speed" || k === "voice" || k === "engine") return;
        if (d[k] == null) return;
        var ctrl = c[k];
        if (ctrl.type === "checkbox") {
          ctrl.checked = !!d[k];
        } else if (ctrl.tagName === "SELECT") {
          // Ensure the default value is present before setting it.
          var defVal = String(d[k]);
          var found = false;
          for (var i = 0; i < ctrl.options.length; i++) {
            if (ctrl.options[i].value === defVal) {
              found = true;
              break;
            }
          }
          if (!found) {
            ctrl.insertBefore(
              U.el("option", { value: defVal, text: defVal }),
              ctrl.firstChild,
            );
          }
          ctrl.value = defVal;
        } else {
          ctrl.value = d[k];
        }
      });
      ["settings-speed", "settings-noise"].forEach(function (id) {
        var s = document.querySelector('[data-testid="' + id + '"]');
        if (s) s.dispatchEvent(new Event("input"));
      });
      toast("Reset to defaults — click Apply or Save to keep them.");
    });
  });
}
