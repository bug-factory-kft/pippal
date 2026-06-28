/* onboarding.js — the ONBOARDING / first-run surface (activation_panel.py
 * parity). Extracted VERBATIM from app.js/main.js (renderOnboarding);
 * behavior-preserving — same DOM, same data-testid values, same bridge
 * calls, same async install-progress path. Isolated as its own
 * module so the onboarding follow-up touches only this file. Shared
 * singletons come from app-core.js; closeWin is shared with the overlay
 * cluster and imported from overlay.js (same single instance the monolith
 * provided). */
"use strict";

import { U, API, view, footer, fail } from "./app-core.js";
import { closeWin } from "./overlay.js";

// ------------------------------------------------------------------
// ONBOARDING / first-run (activation_panel.py parity).
// ------------------------------------------------------------------
export function renderOnboarding() {
  return Promise.all([
    API.call("get_readiness"),
    API.call("get_activation_state"),
  ]).then(function (res) {
    var rd = res[0],
      st = res[1];
    view.innerHTML = "";
    footer.classList.add("hidden");

    var title, subtitle;
    if (rd.status === "missing_piper") {
      title = "PipPal needs a local reading engine";
      subtitle =
        "The tray app is running so you can repair setup or switch engines.";
    } else if (rd.status === "missing_voice") {
      title = "PipPal needs a local voice";
      subtitle =
        "Install an offline voice before the first reading test.\n" +
        "No account. No telemetry. No cloud TTS.";
    } else {
      title = "PipPal is ready to read locally";
      subtitle =
        "PipPal reads selected text aloud on this PC.\n" +
        "No account. No telemetry. No cloud TTS.\n" +
        "Let's make sure you can hear it now.";
    }
    view.appendChild(
      U.el("div", {
        class: "title",
        testid: "onboarding-title",
        text: title,
      }),
    );
    view.appendChild(U.el("div", { class: "subtitle", text: subtitle }));
    view.appendChild(U.el("div", { style: "height:16px" }));

    var statusEl = U.el("div", {
      class: "card-hint",
      testid: "onboarding-status",
      text: st.is_complete
        ? "Done. PipPal can read selected text on this PC."
        : rd.message,
    });
    view.appendChild(
      U.card("Local voice check", [
        U.el("div", {
          class: "card-label",
          testid: "onboarding-engine",
          text: rd.engine_label,
        }),
        U.el("div", {
          class: "card-label",
          text: "Voice: " + rd.voice_label,
        }),
        U.el("div", {
          class: "card-label",
          text: "Hotkey: " + rd.hotkey_label,
        }),
        statusEl,
      ]),
    );

    var sampleBox = U.el("textarea", {
      testid: "onboarding-sample",
      class: "notices-text",
      rows: "2",
      style:
        "width:100%;background:var(--bg-input);border:0;border-radius:6px;" +
        "padding:8px;resize:none;color:var(--text)",
    });
    sampleBox.value = rd.sample_text;
    view.appendChild(
      U.card("Try it in any app", [
        U.el("div", {
          class: "card-label",
          text: "Select text in a browser, PDF, document, or this box.",
        }),
        U.el("div", { style: "height:8px" }),
        sampleBox,
      ]),
    );

    var actions = U.el("div", {
      class: "row",
      testid: "onboarding-actions",
      style: "justify-content:flex-end",
    });

    function btn(text, testid, primary, handler) {
      var b = U.el("button", { text: text, testid: testid });
      if (primary) b.className = "primary";
      b.addEventListener("click", handler);
      return b;
    }

    if (rd.status === "missing_piper") {
      actions.appendChild(btn("Close", "onboarding-close", false, closeWin));
      actions.appendChild(
        btn("Open Settings", "onboarding-open-settings", false, function () {
          API.call("open_settings_window").catch(fail);
        }),
      );
      actions.appendChild(
        btn(
          "Open setup instructions",
          "onboarding-open-setup",
          true,
          function () {
            API.call(
              "open_url",
              "https://github.com/bug-factory-kft/pippal#readme",
            );
          },
        ),
      );
      view.appendChild(actions);
    } else if (rd.status === "missing_voice") {
      // Progress wrap for the "Install default voice" async path.
      var odvProgressWrap = U.el("div", {
        class: "install-progress-wrap",
        testid: "onboarding-install-progress",
      });
      odvProgressWrap.style.display = "none";
      var odvProgressBar = U.el("div", { class: "install-progress-bar" });
      var odvProgressFill = U.el("div", {
        class: "install-progress-fill",
        testid: "onboarding-install-progress-fill",
      });
      odvProgressBar.appendChild(odvProgressFill);
      var odvProgressLabel = U.el("div", {
        class: "install-progress-label",
        testid: "onboarding-install-progress-label",
        text: "",
      });
      odvProgressWrap.appendChild(odvProgressBar);
      odvProgressWrap.appendChild(odvProgressLabel);

      function _pollDefaultVoiceInstall(taskId, installBtn) {
        API.call("voice_install_status", taskId)
          .then(function (s) {
            var pct = s.pct || 0;
            odvProgressFill.style.width = Math.min(100, pct) + "%";
            // The backend status string already contains size + pct + speed;
            // Append a bare "(N%)" only when the status text lacks one.
            var lbl = s.status || "";
            if (pct > 0 && pct < 100 && lbl.indexOf("%") < 0) {
              lbl += "  (" + Math.round(pct) + "%)";
            }
            odvProgressLabel.textContent = lbl;
            if (s.done) {
              odvProgressWrap.style.display = "none";
              if (installBtn) installBtn.disabled = false;
              if (s.error || s.cancelled) {
                statusEl.textContent = s.cancelled ? "Install cancelled." : "Install failed.";
                return;
              }
              return renderOnboarding();
            }
            setTimeout(function () { _pollDefaultVoiceInstall(taskId, installBtn); }, 350);
          })
          .catch(function () {
            setTimeout(function () { _pollDefaultVoiceInstall(taskId, installBtn); }, 800);
          });
      }

      actions.appendChild(
        btn("Skip for now", "onboarding-skip", false, closeWin),
      );
      actions.appendChild(
        btn("Open Voice Manager", "onboarding-open-vm", false, function () {
          API.call("open_voice_manager_window").catch(fail);
        }),
      );
      var odvInstallBtn = btn(
        "Install default voice",
        "onboarding-install-voice",
        true,
        function () {
          odvInstallBtn.disabled = true;
          statusEl.textContent = "";
          odvProgressWrap.style.display = "";
          odvProgressFill.style.width = "0%";
          odvProgressLabel.textContent = "Starting…";
          // Use async path for progress feedback.
          API.call("install_default_voice_async")
            .then(function (r) {
              if (!r || !r.task_id) {
                // Fallback: no async support — sync path (no progress)
                return API.call("install_default_voice")
                  .then(function () {
                    odvProgressWrap.style.display = "none";
                    return renderOnboarding();
                  });
              }
              _pollDefaultVoiceInstall(r.task_id, odvInstallBtn);
            })
            .catch(function (e) {
              odvProgressWrap.style.display = "none";
              odvInstallBtn.disabled = false;
              fail(e);
            });
        },
      );
      actions.appendChild(odvInstallBtn);
      // Anchor progress immediately above the action buttons in a shared
      // bottom container so it is always visible with the button row.
      var odbottom = U.el("div", {
        class: "onboarding-bottom",
        testid: "onboarding-bottom",
      });
      odbottom.appendChild(odvProgressWrap);
      odbottom.appendChild(actions);
      view.appendChild(odbottom);
    } else {
      actions.appendChild(
        btn("Open Settings", "onboarding-open-settings", false, function () {
          API.call("open_settings_window").catch(fail);
        }),
      );
      var played = { v: false };
      var finishBtn = btn(
        st.is_complete ? "Close" : "Finish setup",
        "onboarding-finish",
        st.is_complete,
        function () {
          if (st.is_complete) {
            closeWin();
            return;
          }
          if (!played.v) {
            statusEl.textContent =
              "Play the sample first, then confirm you heard it.";
            return;
          }
          API.call("mark_activation_complete")
            .then(function () {
              statusEl.textContent =
                "Done. PipPal can read selected text on this PC.";
              setTimeout(closeWin, 900);
            })
            .catch(fail);
        },
      );
      if (!st.is_complete) finishBtn.disabled = true;
      var playBtn = btn(
        st.is_complete ? "Play sample again" : "Play sample",
        "onboarding-play-sample",
        !st.is_complete,
        function () {
          API.call("play_sample")
            .then(function () {
              played.v = true;
              finishBtn.disabled = false;
              statusEl.textContent = st.is_complete
                ? "Playing sample again. PipPal is already set up."
                : "Playing sample. If you can hear it, finish setup.";
            })
            .catch(fail);
        },
      );
      actions.appendChild(finishBtn);
      actions.appendChild(playBtn);
      view.appendChild(actions);
    }
  });
}
