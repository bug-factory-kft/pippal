/* voices.js — the VOICE MANAGER surface (voice_manager.py parity, extended
 * Pro catalogue). Extracted VERBATIM from app.js/main.js (vmState,
 * renderVoiceManager, voiceRow); behavior-preserving — same DOM, same
 * data-testid values, same bridge calls, same install-progress UX (#252).
 * Shared singletons/helpers come from app-core.js. */
"use strict";

import {
  U,
  API,
  view,
  footer,
  toast,
  fail,
  confirmDialog,
  signalInstalledVoicesChanged,
} from "./app-core.js";

// ------------------------------------------------------------------
// VOICE MANAGER (voice_manager.py parity — extended Pro catalogue).
// ------------------------------------------------------------------
var vmState = {
  all: [],
  lang: "__all__",
  quality: "Any",
  status: "Any",
  q: "",
};

export function renderVoiceManager() {
  return API.call("get_voice_catalogue").then(function (cat) {
    vmState.all = cat.voices;
    document.getElementById("brand-name").textContent = "Voices";
    view.innerHTML = "";
    footer.classList.add("hidden");

    var langOpts = [{ value: "__all__", label: "All languages" }].concat(
      cat.languages.map(function (l) {
        return { value: l.code, label: l.name };
      }),
    );
    var langSel = U.select("vm-language", langOpts, vmState.lang);
    var qualSel = U.select(
      "vm-quality",
      ["Any", "high", "medium", "low", "x_low"].map(function (q) {
        return { value: q, label: q };
      }),
      vmState.quality,
    );
    var statSel = U.select(
      "vm-status",
      ["Any", "Installed", "Not installed"].map(function (s) {
        return { value: s, label: s };
      }),
      vmState.status,
    );
    var searchInp = U.el("input", {
      type: "text",
      testid: "vm-search",
      placeholder: "",
    });
    searchInp.classList.add("grow");

    langSel.addEventListener("change", function () {
      vmState.lang = langSel.value;
      refreshRows();
    });
    qualSel.addEventListener("change", function () {
      vmState.quality = qualSel.value;
      refreshRows();
    });
    statSel.addEventListener("change", function () {
      vmState.status = statSel.value;
      refreshRows();
    });
    var debounce;
    searchInp.addEventListener("input", function () {
      clearTimeout(debounce);
      debounce = setTimeout(function () {
        vmState.q = searchInp.value.trim().toLowerCase();
        refreshRows();
      }, 180);
    });

    var filterBar = U.el("div", { class: "card" }, [
      U.el("div", { class: "row" }, [
        U.el("label", {
          class: "field-label",
          text: "Language",
          style: "flex:0 0 80px;width:80px",
        }),
        langSel,
        U.el("label", {
          class: "field-label",
          text: "Quality",
          style: "flex:0 0 64px;width:64px",
        }),
        qualSel,
        U.el("label", {
          class: "field-label",
          text: "Status",
          style: "flex:0 0 56px;width:56px",
        }),
        statSel,
      ]),
      U.el("div", { class: "row" }, [
        U.el("label", {
          class: "field-label",
          text: "Search",
          style: "flex:0 0 80px;width:80px",
        }),
        searchInp,
      ]),
    ]);
    view.appendChild(filterBar);
    var rowsWrap = U.el("div", { testid: "vm-rows" });
    view.appendChild(rowsWrap);

    function refreshRows() {
      rowsWrap.innerHTML = "";
      var shown = 0;
      vmState.all.forEach(function (v) {
        if (vmState.lang !== "__all__" && v.lang !== vmState.lang) return;
        if (vmState.quality !== "Any" && v.quality !== vmState.quality)
          return;
        if (vmState.status === "Installed" && !v.installed) return;
        if (vmState.status === "Not installed" && v.installed) return;
        if (vmState.q) {
          var hay = (v.id + " " + v.name + " " + v.label).toLowerCase();
          if (hay.indexOf(vmState.q) < 0) return;
        }
        rowsWrap.appendChild(voiceRow(v, refreshRows));
        shown++;
      });
      if (shown === 0) {
        rowsWrap.appendChild(
          U.el("div", {
            class: "empty",
            testid: "vm-empty",
            text: "No voices match. Clear the filter to see everything.",
          }),
        );
      }
    }
    refreshRows();
  });
}

function voiceRow(v, onChanged) {
  var statusEl = U.el("span", {
    class: "vstatus" + (v.installed ? " ok" : ""),
    testid: "vm-status-" + v.id,
    text: v.installed ? "✓ installed" : "",
  });
  var btn = U.el("button", {
    testid: "vm-action-" + v.id,
    text: v.installed ? "Remove" : "Install",
    class: v.installed ? "danger" : "",
  });
  // Progress bar + cancel button for install (issue #252)
  var voiceCancelBtn = U.el("button", {
    testid: "vm-cancel-" + v.id,
    text: "Cancel",
    class: "btn-secondary",
  });
  voiceCancelBtn.style.display = "none";
  var voiceProgressWrap = U.el("div", {
    class: "install-progress-wrap",
    testid: "vm-progress-" + v.id,
  });
  voiceProgressWrap.style.display = "none";
  var voiceProgressFill = U.el("div", {
    class: "install-progress-fill",
    testid: "vm-progress-fill-" + v.id,
  });
  var voiceProgressBar = U.el("div", { class: "install-progress-bar" });
  voiceProgressBar.appendChild(voiceProgressFill);
  var voiceProgressLabel = U.el("div", {
    class: "install-progress-label",
    testid: "vm-progress-label-" + v.id,
    text: "",
  });
  voiceProgressWrap.appendChild(voiceProgressBar);
  voiceProgressWrap.appendChild(voiceProgressLabel);

  var _installTaskId = null;

  function _stopInstallUI(clearStatus) {
    voiceCancelBtn.style.display = "none";
    voiceCancelBtn.disabled = false;
    voiceProgressWrap.style.display = "none";
    btn.disabled = false;
    if (clearStatus) {
      statusEl.textContent = "";
      statusEl.className = "vstatus";
    }
    _installTaskId = null;
  }

  function _pollVoiceInstall(taskId) {
    API.call("voice_install_status", taskId)
      .then(function (s) {
        var pct = s.pct || 0;
        voiceProgressFill.style.width = Math.min(100, pct) + "%";
        var lbl = s.status || "";
        if (pct > 0 && pct < 100 && lbl.indexOf("%") < 0) {
          lbl += "  (" + Math.round(pct) + "%)";
        }
        voiceProgressLabel.textContent = lbl;
        // statusEl (.vstatus span) is intentionally NOT updated here to prevent
        // the duplicate-indicator layout break (#252); it is cleared in doInstall
        // and only restored on completion/failure via _stopInstallUI.
        if (s.done) {
          if (s.cancelled || s.error) {
            _stopInstallUI(true);
            if (s.cancelled) toast("Voice install cancelled.");
            else { statusEl.textContent = "failed"; statusEl.className = "vstatus err"; toast("Voice install failed: " + (s.error || "unknown error"), true); }
            return;
          }
          _stopInstallUI(false);
          // Re-fetch catalogue to sync vmState.all, then update THIS row
          // in-place.  Do NOT call onChanged()/refreshRows() here — that
          // wipes rowsWrap.innerHTML and destroys any other in-progress
          // voice row (including its poll loop and progress DOM), which is
          // the concurrent-download bug (fix/voice-download-per-row).
          return API.call("get_voice_catalogue").then(function (cat) {
            vmState.all = cat.voices;
            // Sync local voice object so btn click-handler sees installed=true.
            var updated = cat.voices.find(function (cv) { return cv.id === v.id; });
            if (updated) { Object.assign(v, updated); } else { v.installed = true; }
            // Update only this row's UI elements in-place.
            statusEl.textContent = "✓ installed";
            statusEl.className = "vstatus ok";
            btn.textContent = "Remove";
            btn.className = "danger";
            signalInstalledVoicesChanged();
            toast("Voice installed — open Settings to make it your active voice.");
          });
        }
        setTimeout(function () { _pollVoiceInstall(taskId); }, 350);
      })
      .catch(function () {
        setTimeout(function () { _pollVoiceInstall(taskId); }, 800);
      });
  }

  function doRemove() {
    btn.disabled = true;
    statusEl.textContent = "removing…";
    API.call("remove_voice", v.id)
      .then(function () {
        // Re-fetch the catalogue so vmState.all reflects the removal
        // before refreshRows() re-renders (mirrors the doInstall fix).
        return API.call("get_voice_catalogue").then(function (cat) {
          vmState.all = cat.voices;
          signalInstalledVoicesChanged();
          onChanged();
        });
      })
      .catch(function (e) {
        btn.disabled = false;
        fail(e);
      });
  }
  function doInstall() {
    btn.disabled = true;
    // Clear legacy status text — progress-wrap is the single indicator (#252)
    statusEl.textContent = "";
    statusEl.className = "vstatus";
    voiceCancelBtn.style.display = "";
    voiceProgressWrap.style.display = "";
    voiceProgressFill.style.width = "0%";
    // Use install_voice_async if available, fall back to sync install_voice
    API.call("install_voice_async", v.id)
      .then(function (r) {
        if (!r || !r.task_id) {
          // Fallback: old sync path (no progress)
          return API.call("install_voice", v.id).then(function (result) {
            _stopInstallUI(false);
            return API.call("get_voice_catalogue").then(function (cat) {
              vmState.all = cat.voices;
              signalInstalledVoicesChanged();
              onChanged();
              toast(
                "Voice installed" +
                  (result && result.installed
                    ? " — open Settings to make it your active voice."
                    : "."),
              );
            });
          });
        }
        _installTaskId = r.task_id;
        _pollVoiceInstall(r.task_id);
      })
      .catch(function (e) {
        _stopInstallUI(false);
        statusEl.textContent = "failed";
        statusEl.className = "vstatus err";
        fail(e);
      });
  }
  voiceCancelBtn.addEventListener("click", function () {
    if (!_installTaskId) return;
    voiceCancelBtn.disabled = true;
    voiceProgressLabel.textContent = "Cancelling…";
    API.call("cancel_voice_install", _installTaskId).catch(function () {});
  });
  btn.addEventListener("click", function () {
    if (v.installed) {
      confirmDialog("Remove voice", "Remove " + v.label + "?").then(
        function (ok) {
          if (ok) doRemove();
        },
      );
    } else {
      doInstall();
    }
  });
  // Progress is placed immediately above the action button row so it is
  // visually anchored to the buttons (#252 UX placement).
  return U.el("div", { class: "card" }, [
    U.el("div", { class: "vrow" }, [
      U.el("div", { class: "vmeta" }, [
        U.el("div", { class: "vname", text: v.label }),
        U.el("div", {
          class: "vsub",
          text: "id: " + v.id + "   ·   " + v.quality,
        }),
      ]),
      statusEl,
    ]),
    voiceProgressWrap,
    U.el("div", {
      class: "vm-action-row",
      testid: "vm-row-actions-" + v.id,
    }, [btn, voiceCancelBtn]),
  ]);
}
