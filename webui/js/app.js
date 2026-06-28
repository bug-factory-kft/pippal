/* app.js — renders one of PipPal's UI surfaces into #view.
 *
 * Which surface is decided by `?view=` in the URL the Python window
 * loads (settings | onboarding | voices | notices | overlay). Every
 * surface is a parity port of the matching Tk window; backend calls
 * go through PipPalAPI so the transport (pywebview bridge vs served
 * HTTP) is invisible here. */
(function () {
  "use strict";
  var U = window.UI, API = window.PipPalAPI;
  var view = document.getElementById("view");
  var footer = document.getElementById("footer");
  var toastEl = document.getElementById("toast");

  var params = new URLSearchParams(location.search);
  var SURFACE = params.get("view") || "settings";

  function toast(msg, isErr) {
    toastEl.textContent = msg;
    toastEl.className = "toast show" + (isErr ? " err" : "");
    clearTimeout(toast._t);
    toast._t = setTimeout(function () { toastEl.className = "toast"; }, 2600);
  }
  window.__pippalToast = toast;

  function fail(e) { toast(String(e && e.message || e), true); }

  // Real modal confirm gate — the web analogue of Tk's
  // messagebox.askyesno. Resolves true only when the user clicks Yes;
  // the destructive caller MUST await this before acting. There is no
  // auto-dismiss: the action is blocked until an explicit choice.
  var confirmModal = document.getElementById("confirm-modal");
  var confirmTitle = document.getElementById("confirm-title");
  var confirmBody = document.getElementById("confirm-body");
  var confirmOk = document.getElementById("confirm-ok");
  var confirmCancel = document.getElementById("confirm-cancel");
  function confirmDialog(title, body) {
    return new Promise(function (resolve) {
      confirmTitle.textContent = title;
      confirmBody.textContent = body;
      confirmModal.classList.remove("hidden");
      function cleanup(result) {
        confirmModal.classList.add("hidden");
        confirmOk.removeEventListener("click", onOk);
        confirmCancel.removeEventListener("click", onCancel);
        resolve(result);
      }
      function onOk() { cleanup(true); }
      function onCancel() { cleanup(false); }
      confirmOk.addEventListener("click", onOk);
      confirmCancel.addEventListener("click", onCancel);
    });
  }
  window.__pippalConfirm = confirmDialog;

  document.getElementById("btn-window-close").addEventListener("click", function () {
    API.call("close_window").catch(function () {});
  });

  // ------------------------------------------------------------------
  // SETTINGS — the seven cards + footer (settings_window.py parity).
  // ------------------------------------------------------------------
  var settingsState = { config: {}, defaults: {}, controls: {}, voiceCombo: null };

  function speedToLengthScale(speed) { return Math.round((1.0 / speed) * 1000) / 1000; }
  function lengthScaleToSpeed(ls) { return ls ? Math.round((1.0 / ls) * 100) / 100 : 1.0; }


  // ------------------------------------------------------------------
  // Diagnostics LOGGING card (settings_cards.py / Pro buildDiagCard parity,
  // MINUS the Pro-only upload half). All controls are backed by the core
  // diagnostics bridge merged in #113: get_diag_state / set_diag_level /
  // open_diag_folder / delete_diag_logs. There is deliberately NO "Send to
  // creator" upload control here -- that feature (send_diag_logs, the upload
  // progress bar, the URL/token fields) lives only in Pro.
  // ------------------------------------------------------------------
  function buildDiagCard(state) {
    state = state || {};

    // 1. Log-level select: Off / Errors only / Full trace -> set_diag_level.
    var levelSel = U.select("settings-diag-level", [
      { value: "off", label: "Off" },
      { value: "error", label: "Errors only" },
      { value: "trace", label: "Full trace" },
    ], state.level || "off");
    levelSel.classList.add("grow");

    // 2. Descriptive / privacy text -- no upload / "send to AI" / "send to
    // creator" sentences (Pro-only).
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

    // 3. Status line: log count · KB · folder path -> get_diag_state.
    function statusText(s) {
      var kb = Math.round((s.total_bytes || 0) / 1024);
      return (s.log_count || 0) + " log file" + (s.log_count === 1 ? "" : "s")
        + "  ·  " + kb + " KB"
        + "  ·  " + (s.folder || "local PipPal folder");
    }
    var statusEl = U.el("div", { class: "card-hint",
      testid: "settings-diag-status", text: statusText(state) });

    function refreshStatus() {
      API.call("get_diag_state").then(function (s) {
        statusEl.textContent = statusText(s);
        levelSel.value = s.level || "off";
      }).catch(function () {});
    }

    // 4. Buttons: Open log folder + Delete logs (danger).
    var openBtn = U.el("button", { testid: "settings-diag-open",
      text: "Open log folder" });
    var deleteBtn = U.el("button", { class: "danger",
      testid: "settings-diag-delete", text: "Delete logs" });

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
      confirmDialog("Delete diagnostics logs",
        "Delete all diagnostics logs? This cannot be undone.").then(function (ok) {
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

  // Voice-refresh teardown: previous renderSettings listener cleanup.
  // Ported from Pro settings.js (~line 39) to prevent duplicate listeners.
  var teardownSettingsVoiceRefresh = null;

  function renderSettings() {
    if (teardownSettingsVoiceRefresh) {
      teardownSettingsVoiceRefresh();
      teardownSettingsVoiceRefresh = null;
    }
    return Promise.all([
      API.call("get_config"),
      API.call("get_defaults"),
      API.call("get_engines"),
      API.call("get_installed_voices"),
      API.call("get_hotkey_actions"),
      API.call("context_menu_status"),
      API.call("about_info"),
      API.call("get_diag_state"),
    ]).then(function (res) {
      var cfg = res[0], defs = res[1], engines = res[2], voices = res[3];
      var hotkeys = res[4], ctxStatus = res[5], about = res[6], diag = res[7];
      settingsState.config = cfg;
      settingsState.defaults = defs;
      settingsState.controls = {};
      document.getElementById("brand-name").textContent = cfg.brand_name || "PipPal";

      view.innerHTML = "";
      footer.classList.remove("hidden");

      // ---- Voice card ----
      var engineSel = U.select("settings-engine",
        engines.map(function (e) { return { value: e, label: e }; }),
        (cfg.engine || "piper"));
      engineSel.classList.add("grow");
      var voiceOpts = voices.length
        ? voices.map(function (v) { return { value: v, label: v }; })
        : [{ value: "", label: "(no voice installed)" }];
      var voiceSel = U.select("settings-voice", voiceOpts,
        voices.indexOf(cfg.voice) >= 0 ? cfg.voice : (voices[0] || ""));
      voiceSel.classList.add("grow");
      if (!voices.length) voiceSel.disabled = true;
      settingsState.controls.engine = engineSel;
      settingsState.controls.voice = voiceSel;
      var manageBtn = U.el("button", {
        testid: "settings-manage-voices",
        text: voices.length ? "Manage…" : "Install voices…",
      });
      manageBtn.addEventListener("click", function () {
        API.call("open_voice_manager_window").catch(fail);
      });
      var engineHint = U.el("div", { class: "card-hint", testid: "settings-engine-hint",
        text: voices.length
          ? "Piper voice. Click Manage to install more from the curated list."
          : "No Piper voice installed yet. Click Install voices to download one." });
      var voiceCard = U.card("Voice", [
        U.fieldRow("Engine", engineSel),
        U.el("div", { class: "row" }, [
          U.el("label", { class: "field-label", text: "Voice" }),
          voiceSel, manageBtn,
        ]),
        engineHint,
      ]);

      // Live-refresh the voice list when voices are installed in the Voices
      // window. Ported from Pro settings.js ~lines 296-327.
      var piperVoiceRefreshToken = 0;
      function refreshPiperVoices() {
        var token = ++piperVoiceRefreshToken;
        return API.call("get_installed_voices")
          .then(function (freshVoices) {
            if (token !== piperVoiceRefreshToken) return;
            voices = Array.isArray(freshVoices) ? freshVoices : [];
            manageBtn.textContent = voices.length ? "Manage…" : "Install voices…";
            var newOpts = voices.length
              ? voices.map(function (v) { return { value: v, label: v }; })
              : [{ value: "", label: "(no voice installed)" }];
            var currentVal = voiceSel.value;
            while (voiceSel.firstChild) voiceSel.removeChild(voiceSel.firstChild);
            newOpts.forEach(function (opt) {
              var o = document.createElement("option");
              o.value = opt.value; o.textContent = opt.label;
              if (opt.value === currentVal) o.selected = true;
              voiceSel.appendChild(o);
            });
            voiceSel.disabled = !voices.length;
          })
          .catch(function () {});
      }
      function _onInstalledVoicesChanged() { refreshPiperVoices(); }
      function _onInstalledVoicesStorage(e) {
        if (e.key === INSTALLED_VOICES_CHANGED_KEY) refreshPiperVoices();
      }
      window.addEventListener(INSTALLED_VOICES_CHANGED_EVENT, _onInstalledVoicesChanged);
      window.addEventListener("storage", _onInstalledVoicesStorage);
      teardownSettingsVoiceRefresh = function () {
        window.removeEventListener(INSTALLED_VOICES_CHANGED_EVENT, _onInstalledVoicesChanged);
        window.removeEventListener("storage", _onInstalledVoicesStorage);
      };

      // ---- Speech card ----
      var speed = U.sliderRow("Speed", "settings-speed", 0.6, 1.7, 0.01,
        lengthScaleToSpeed(parseFloat(cfg.length_scale || 1.0)),
        function (v) { return v.toFixed(2) + "×"; });
      var noise = U.sliderRow("Variation", "settings-noise", 0.3, 1.0, 0.01,
        parseFloat(cfg.noise_scale != null ? cfg.noise_scale : 0.667),
        function (v) { return v.toFixed(2); });
      settingsState.controls.speed = speed.slider;
      settingsState.controls.noise_scale = noise.slider;
      var speechCard = U.card("Speech", [
        speed.node, noise.node,
        U.hint("Speed: 0.6× clearer · 1.0× normal · 1.7× faster.   "
              + "Variation: livelier intonation at higher values."),
      ]);

      // ---- Hotkeys card ----
      var hkRows = [];
      hotkeys.forEach(function (a) {
        var key = a[1], label = a[2], def = a[3];
        var inp = U.el("input", { type: "text", testid: "settings-" + key });
        inp.classList.add("grow");
        inp.value = cfg[key] != null ? cfg[key] : def;
        settingsState.controls[key] = inp;
        hkRows.push(U.fieldRow(label, inp));
      });
      hkRows.push(U.hint("Format: windows+shift+r · ctrl+alt+space · "
        + "alt+shift+f1 …  Captured combos are suppressed (other apps "
        + "won't also see them)."));
      var hotkeysCard = U.card("Hotkeys", hkRows);

      // ---- Reader panel card ----
      var showPanel = U.checkRow("settings-show_overlay",
        "Show panel while reading", cfg.show_overlay);
      var showText = U.checkRow("settings-show_text_in_overlay",
        "Show text with karaoke highlight", cfg.show_text_in_overlay);
      settingsState.controls.show_overlay = showPanel.querySelector("input");
      settingsState.controls.show_text_in_overlay = showText.querySelector("input");
      var autoHide = U.spinRow("Auto-hide delay", "settings-auto_hide_ms",
        300, 8000, 100, cfg.auto_hide_ms != null ? cfg.auto_hide_ms : 1500, "ms");
      var distance = U.spinRow("Distance from taskbar", "settings-overlay_y_offset",
        20, 600, 10, cfg.overlay_y_offset != null ? cfg.overlay_y_offset : 100, "px");
      var karaoke = U.spinRow("Karaoke offset", "settings-karaoke_offset_ms",
        -300, 600, 20, cfg.karaoke_offset_ms != null ? cfg.karaoke_offset_ms : 120,
        "ms (positive = highlight waits, negative = highlight leads)");
      settingsState.controls.auto_hide_ms = autoHide.input;
      settingsState.controls.overlay_y_offset = distance.input;
      settingsState.controls.karaoke_offset_ms = karaoke.input;
      var panelCard = U.card("Reader panel", [
        showPanel, showText, autoHide.node, distance.node, karaoke.node,
      ]);

      // ---- Windows integration card ----
      var ctxStatusEl = U.el("div", { class: "card-label", testid: "settings-ctx-status",
        text: ctxText(ctxStatus) });
      var installBtn = U.el("button", { testid: "settings-ctx-install", text: "Install" });
      var removeBtn = U.el("button", { class: "danger", testid: "settings-ctx-remove",
        text: "Remove" });
      installBtn.addEventListener("click", function () {
        API.call("install_context_menu").then(function (st) {
          ctxStatusEl.textContent = ctxText(st);
          toast("Right-click entry installed for .txt and .md.");
        }).catch(fail);
      });
      removeBtn.addEventListener("click", function () {
        API.call("remove_context_menu").then(function (st) {
          ctxStatusEl.textContent = ctxText(st);
        }).catch(fail);
      });
      var intCard = U.card("Windows integration", [
        ctxStatusEl,
        U.hint("Adds a 'Read with PipPal' entry to the right-click menu of "
          + ".txt and .md files in File Explorer (current user only)."),
        U.el("div", { class: "row", style: "margin-top:8px" }, [installBtn, removeBtn]),
      ]);

      // ---- Open-source notices card ----
      var noticesBtn = U.el("button", { testid: "settings-view-licences",
        text: "View licences…" });
      noticesBtn.addEventListener("click", function () {
        API.call("open_notices_window").catch(fail);
      });
      var noticesCard = U.card("Open-source notices", [
        U.hint("PipPal uses open-source libraries and local TTS runtime "
          + "artifacts. Their licences are included with this install or "
          + "source checkout."),
        U.el("div", { class: "row", style: "margin-top:8px" }, [noticesBtn]),
      ]);

      // ---- About card ----
      var linkRow = U.el("div", { class: "link-row" }, about.links.map(function (l) {
        var a = U.el("span", { class: "link", text: l.text, testid: "about-" + l.key });
        a.addEventListener("click", function () { API.call("open_url", l.url); });
        return a;
      }));
      var aboutCard = U.card("About", [
        U.el("div", { class: "card-label", style: "font-family:var(--font-semibold)",
          text: (cfg.brand_name || "PipPal") + " " + about.version }),
        U.el("div", { class: "card-hint", text: "Your little offline reading buddy." }),
        U.el("div", { class: "card-hint", style: "margin-top:8px",
          text: "© 2026 Bug Factory Kft.  ·  Offline-first by design." }),
        linkRow,
      ]);

      view.appendChild(voiceCard);
      view.appendChild(speechCard);
      view.appendChild(hotkeysCard);
      view.appendChild(panelCard);
      view.appendChild(intCard);
      view.appendChild(buildDiagCard(diag));
      view.appendChild(noticesCard);
      view.appendChild(aboutCard);
    });
  }

  function ctxText(status) {
    if (status === "all") return "✓ Right-click entry installed for .txt and .md.";
    if (status === "partial") return "⚠ Partial install — re-run Install to fix.";
    return "○ Right-click entry not installed.";
  }

  function collectSettingsValues() {
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
    if (c.voice && c.voice.value) values.voice = c.voice.value;
    Object.keys(c).forEach(function (k) {
      if (k.indexOf("hotkey_") === 0) values[k] = (c[k].value || "").trim().toLowerCase();
    });
    return values;
  }

  function persist(close) {
    return API.call("save_config", collectSettingsValues(), close)
      .then(function (r) {
        if (r && r.hotkey_failures && r.hotkey_failures.length) {
          toast("Saved, but some hotkeys could not be bound.", true);
        } else {
          toast(close ? "Saved." : "Applied.");
        }
        if (close) {
          return API.call("close_window").catch(function () {
            // Fallback: if close_window fails (e.g. headless/served mode),
            // re-render settings so the UI stays consistent.
            return renderSettings();
          });
        }
        return renderSettings();
      })
      .catch(fail);
  }

  function wireFooter() {
    document.getElementById("btn-save").addEventListener("click", function () {
      persist(true);
    });
    document.getElementById("btn-apply").addEventListener("click", function () {
      persist(false);
    });
    document.getElementById("btn-cancel").addEventListener("click", function () {
      API.call("close_window").catch(function () {});
    });
    document.getElementById("btn-reset").addEventListener("click", function () {
      // Tk parity: messagebox.askyesno("Reset to defaults", "Reset
      // every field to its built-in default? Click Apply or Save
      // afterwards to keep them.") — the form must NOT change until
      // the user accepts; Cancel leaves every field as-is.
      confirmDialog(
        "Reset to defaults",
        "Reset every field to its built-in default? "
          + "Click Apply or Save afterwards to keep them."
      ).then(function (ok) {
        if (!ok) return;
        var d = settingsState.defaults, c = settingsState.controls;
        if (d.length_scale != null && c.speed)
          c.speed.value = lengthScaleToSpeed(parseFloat(d.length_scale));
        Object.keys(c).forEach(function (k) {
          if (k === "speed" || k === "voice" || k === "engine") return;
          if (d[k] == null) return;
          var ctrl = c[k];
          if (ctrl.type === "checkbox") ctrl.checked = !!d[k];
          else ctrl.value = d[k];
        });
        ["settings-speed", "settings-noise"].forEach(function (id) {
          var s = document.querySelector('[data-testid="' + id + '"]');
          if (s) s.dispatchEvent(new Event("input"));
        });
        toast("Reset to defaults — click Apply or Save to keep them.");
      });
    });
  }

  // ------------------------------------------------------------------
  // ONBOARDING / first-run (activation_panel.py parity).
  // ------------------------------------------------------------------
  function renderOnboarding() {
    return Promise.all([
      API.call("get_readiness"), API.call("get_activation_state"),
    ]).then(function (res) {
      var rd = res[0], st = res[1];
      view.innerHTML = "";
      footer.classList.add("hidden");

      var title, subtitle;
      if (rd.status === "missing_piper") {
        title = "PipPal needs a local reading engine";
        subtitle = "The tray app is running so you can repair setup or switch engines.";
      } else if (rd.status === "missing_voice") {
        title = "PipPal needs a local voice";
        subtitle = "Install an offline voice before the first reading test.\n"
          + "No account. No telemetry. No cloud TTS.";
      } else {
        title = "PipPal is ready to read locally";
        subtitle = "PipPal reads selected text aloud on this PC.\n"
          + "No account. No telemetry. No cloud TTS.\n"
          + "Let's make sure you can hear it now.";
      }
      view.appendChild(U.el("div", { class: "title", testid: "onboarding-title",
        text: title }));
      view.appendChild(U.el("div", { class: "subtitle", text: subtitle }));
      view.appendChild(U.el("div", { style: "height:16px" }));

      var statusEl = U.el("div", { class: "card-hint", testid: "onboarding-status",
        text: st.is_complete ? "Done. PipPal can read selected text on this PC."
                             : rd.message });
      view.appendChild(U.card("Local voice check", [
        U.el("div", { class: "card-label", testid: "onboarding-engine",
          text: rd.engine_label }),
        U.el("div", { class: "card-label", text: "Voice: " + rd.voice_label }),
        U.el("div", { class: "card-label", text: "Hotkey: " + rd.hotkey_label }),
        statusEl,
      ]));

      var sampleBox = U.el("textarea", { testid: "onboarding-sample",
        class: "notices-text", rows: "2",
        style: "width:100%;background:var(--bg-input);border:0;border-radius:6px;"
             + "padding:8px;resize:none;color:var(--text)" });
      sampleBox.value = rd.sample_text;
      view.appendChild(U.card("Try it in any app", [
        U.el("div", { class: "card-label",
          text: "Select text in a browser, PDF, document, or this box." }),
        U.el("div", { style: "height:8px" }),
        sampleBox,
      ]));

      var actions = U.el("div", { class: "row", style: "justify-content:flex-end" });

      function btn(text, testid, primary, handler) {
        var b = U.el("button", { text: text, testid: testid });
        if (primary) b.className = "primary";
        b.addEventListener("click", handler);
        return b;
      }

      if (rd.status === "missing_piper") {
        actions.appendChild(btn("Close", "onboarding-close", false, closeWin));
        actions.appendChild(btn("Open Settings", "onboarding-open-settings", false,
          function () { API.call("open_settings_window").catch(fail); }));
        actions.appendChild(btn("Open setup instructions", "onboarding-open-setup",
          true, function () {
            API.call("open_url", "https://github.com/bug-factory-kft/pippal#readme");
          }));
      } else if (rd.status === "missing_voice") {
        actions.appendChild(btn("Skip for now", "onboarding-skip", false, closeWin));
        actions.appendChild(btn("Open Voice Manager", "onboarding-open-vm", false,
          function () { API.call("open_voice_manager_window").catch(fail); }));
        actions.appendChild(btn("Install default voice", "onboarding-install-voice",
          true, function () {
            statusEl.textContent = "Installing default English voice…";
            API.call("install_default_voice").then(function () {
              return renderOnboarding();
            }).catch(fail);
          }));
      } else {
        actions.appendChild(btn("Skip for now", "onboarding-skip", false, closeWin));
        actions.appendChild(btn("Open Settings", "onboarding-open-settings", false,
          function () { API.call("open_settings_window").catch(fail); }));
        var played = { v: false };
        var finishBtn = btn(st.is_complete ? "Close" : "Finish setup",
          "onboarding-finish", st.is_complete, function () {
            if (st.is_complete) { closeWin(); return; }
            if (!played.v) {
              statusEl.textContent =
                "Play the sample first, then confirm you heard it.";
              return;
            }
            API.call("mark_activation_complete").then(function () {
              statusEl.textContent = "Done. PipPal can read selected text on this PC.";
              setTimeout(closeWin, 900);
            }).catch(fail);
          });
        if (!st.is_complete) finishBtn.disabled = true;
        var playBtn = btn(st.is_complete ? "Play sample again" : "Play sample",
          "onboarding-play-sample", !st.is_complete, function () {
            API.call("play_sample").then(function () {
              played.v = true;
              finishBtn.disabled = false;
              statusEl.textContent = st.is_complete
                ? "Playing sample again. PipPal is already set up."
                : "Playing sample. If you can hear it, finish setup.";
            }).catch(fail);
          });
        actions.appendChild(finishBtn);
        actions.appendChild(playBtn);
      }
      view.appendChild(actions);
    });
  }

  // ------------------------------------------------------------------
  // VOICE MANAGER (voice_manager.py parity — extended Pro catalogue).
  // ------------------------------------------------------------------
  // Inline helper — signals other windows (e.g. Settings) that the
  // installed voice list has changed.  Ported verbatim from Pro's
  // app-core.js signalInstalledVoicesChanged (lines 64–84).
  var INSTALLED_VOICES_CHANGED_EVENT = "pippal-installed-voices-changed";
  var INSTALLED_VOICES_CHANGED_KEY = "pippal:installed-voices-changed";
  function signalInstalledVoicesChanged() {
    var stamp = String(Date.now());
    try {
      localStorage.setItem(INSTALLED_VOICES_CHANGED_KEY, stamp);
    } catch (e) {
      if (window.console && console.warn) {
        console.warn("Could not notify other windows about voice changes.", e);
      }
    }
    try {
      window.dispatchEvent(
        new CustomEvent(INSTALLED_VOICES_CHANGED_EVENT, {
          detail: { stamp: stamp },
        }),
      );
    } catch (e) {
      if (window.console && console.warn) {
        console.warn("Could not notify this window about voice changes.", e);
      }
    }
  }

  // Pro voices.js 22–339 verbatim (IIFE-adapted: no import/export lines).
  var vmState = {
    all: [],
    lang: "__all__",
    quality: "Any",
    status: "Any",
    q: "",
  };

  function renderVoiceManager() {
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

  // ------------------------------------------------------------------
  // NOTICES viewer (notices_card.py _NoticesViewer parity).
  // ------------------------------------------------------------------
  function renderNotices() {
    return API.call("get_notices").then(function (text) {
      document.getElementById("brand-name").textContent =
        "PipPal - Open-source licences";
      footer.classList.add("hidden");
      view.innerHTML = "";
      view.appendChild(U.el("div", { class: "notices-text", testid: "notices-body",
        text: text }));
    });
  }

  // ------------------------------------------------------------------
  // Pro overlay.js 27–545 verbatim (IIFE-adapted: no import/export lines;
  // closeWin kept below as free's existing version).
  // ------------------------------------------------------------------
  // Playful loading messages (#6) — whimsical, fake-technical lines in
  // the charming STYLE of classic life-sim loading screens, tailored to
  // a text-to-speech READER. ORIGINAL strings (no trademarked phrases).
  // The UI language is English (cf. "PipPal Pro", "Loading…"), so these
  // are English. They rotate while the overlay is in the loading/thinking
  // state; see the rotation logic in tick() below.
  // ------------------------------------------------------------------
  var LOADING_MESSAGES = [
    "Warming up the vocal cords…",
    "Reticulating syllables…",
    "Teaching the narrator to breathe…",
    "Summoning the perfect voice…",
    "Untangling the sentences…",
    "Polishing the consonants…",
    "Brewing a fresh batch of phonemes…",
    "Tuning the inner monologue…",
    "Coaxing vowels into formation…",
    "Rehearsing the dramatic pauses…",
    "Buffering a little eloquence…",
    "Smoothing out the syllables…",
    "Calibrating the storyteller…",
    "Gathering the right intonation…",
  ];
  // Each rotating message is shown for this long before advancing.
  var LOADING_ROTATE_MS = 1800;
  // Random starting offset so different reads don't always begin the same.
  var loadingMsgBase = Math.floor(Math.random() * LOADING_MESSAGES.length);
  function currentLoadingMessage() {
    var step = Math.floor(Date.now() / LOADING_ROTATE_MS);
    var idx = (loadingMsgBase + step) % LOADING_MESSAGES.length;
    return LOADING_MESSAGES[idx];
  }

  // #6 — AI shortcuts (summary / explain / translate / define) set the
  // backend ``action_label`` to a bare one-word action id (e.g. "summary",
  // or "translate · en"). Showing that raw id as the loader text is ugly and
  // breaks the playful rotating-message experience. Instead, for AI actions
  // we lead with a friendly action-specific line and then keep ROTATING the
  // whimsical loading set, so the loader stays varied and charming rather
  // than freezing on the bare word. The action id is the part before any
  // " · …" suffix (translate carries the target language after the dot).
  // Pro-only AI path, inert in free (action_label is never a bare AI id here).
  var AI_ACTION_LINES = {
    summary: "Distilling the key points…",
    explain: "Gathering an explanation…",
    translate: "Switching languages…",
    define: "Looking it up…",
  };
  function aiActionId(label) {
    if (!label) return null;
    var id = String(label).split("·")[0].trim().toLowerCase();
    return Object.prototype.hasOwnProperty.call(AI_ACTION_LINES, id) ? id : null;
  }
  // Loader text for an AI action: alternate the friendly action line with the
  // playful rotating set so the loader stays lively for the whole synth.
  function aiLoadingMessage(actionId) {
    var step = Math.floor(Date.now() / LOADING_ROTATE_MS);
    // Even steps show the action-specific friendly line; odd steps show a
    // rotating whimsical message — never the bare action id.
    if (step % 2 === 0) return AI_ACTION_LINES[actionId];
    return currentLoadingMessage();
  }
  function escapeLoadingText(s) {
    return String(s).replace(/[<>&"]/g, function (c) {
      return { "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;" }[c];
    });
  }

  // ------------------------------------------------------------------
  // READER OVERLAY panel (overlay.py / overlay_paint.py parity).
  // Window architecture: NORMAL opaque frameless window. Drag uses the
  // .pywebview-drag-region mechanism on the brand area. Transport buttons
  // and close button are siblings (NOT descendants) so clicks never
  // trigger a window drag.
  // ------------------------------------------------------------------
  function renderOverlay() {
    document.body.classList.add("overlay-mode");
    document.getElementById("titlebar").classList.add("hidden");
    footer.classList.add("hidden");
    view.style.padding = "0";
    view.innerHTML = "";

    var dot = U.el("span", { class: "overlay-dot", testid: "overlay-dot" });
    var label = U.el("span", {
      class: "ohlabel",
      testid: "overlay-label",
      text: "PipPal Pro",
    });
    // Brand area: icon + dot + label wrapped in a drag region.
    var dragRegion = U.el(
      "span",
      { class: "overlay-drag-region pywebview-drag-region", testid: "overlay-drag-region" },
      [U.el("img", { src: "assets/pippal_icon.png" }), dot, label],
    );
    var closeBtn = U.el("button", {
      class: "overlay-close",
      testid: "overlay-close",
    });
    var bodyEl = U.el("div", { class: "overlay-body", testid: "overlay-text" });
    // #281.6 loading indicator: shown while synthesis is in progress,
    // hidden during reading/idle/done.
    var loadingEl = U.el("div", {
      class: "overlay-loading hidden",
      testid: "overlay-loading",
    });
    var barFill = U.el("div");
    var counter = U.el("span", {
      class: "overlay-counter",
      testid: "overlay-page-marker",
      text: "",
    });
    var legacyCounterMarker = U.el("span", {
      testid: "overlay-counter",
      "aria-hidden": "true",
      style: "display:none",
      text: "",
    });
    // SVG icon helpers — all icons share the same 16×16 viewBox.
    function svgIcon(pathD, extraAttrs) {
      var ns = "http://www.w3.org/2000/svg";
      var svg = document.createElementNS(ns, "svg");
      svg.setAttribute("viewBox", "0 0 16 16");
      svg.setAttribute("width", "14");
      svg.setAttribute("height", "14");
      svg.setAttribute("aria-hidden", "true");
      svg.setAttribute("fill", "currentColor");
      if (extraAttrs) {
        Object.keys(extraAttrs).forEach(function (k) {
          svg.setAttribute(k, extraAttrs[k]);
        });
      }
      var path = document.createElementNS(ns, "path");
      path.setAttribute("d", pathD);
      svg.appendChild(path);
      return svg;
    }
    var ICONS = {
      prev:   "M2 3h1.5v10H2V3zm10.5 1.06L6.06 8l6.44 3.94V4.06z",
      replay: "M8 2.5a5.5 5.5 0 1 0 5.5 5.5h-1.5A4 4 0 1 1 8 4v1.5l3-2.25L8 1V2.5z",
      pause:  "M4 3h2.5v10H4V3zm5.5 0H12v10H9.5V3z",
      play:   "M4 3.06v9.88L13 8 4 3.06z",
      next:   "M12.5 3H14v10h-1.5V3zM3.5 4.06v7.88L9.94 8 3.5 4.06z",
      close:  "M3.22 3.22a.75.75 0 0 1 1.06 0L8 6.94l3.72-3.72a.75.75 0 1 1 1.06 1.06L9.06 8l3.72 3.72a.75.75 0 1 1-1.06 1.06L8 9.06l-3.72 3.72a.75.75 0 0 1-1.06-1.06L6.94 8 3.22 4.28a.75.75 0 0 1 0-1.06z",
    };
    closeBtn.appendChild(svgIcon(ICONS.close));
    function obtn(tag) {
      var b = U.el("button", { class: "obtn", testid: "overlay-" + tag });
      b.appendChild(svgIcon(ICONS[tag]));
      b.addEventListener("click", function () {
        API.call("overlay_action", tag).catch(fail);
      });
      return b;
    }
    var prevBtn   = obtn("prev");
    var replayBtn = obtn("replay");
    var pauseBtn  = obtn("pause");
    var nextBtn   = obtn("next");
    var head = U.el("div", { class: "overlay-head" }, [
      dragRegion, prevBtn, replayBtn, pauseBtn, nextBtn, closeBtn,
    ]);
    var progress = U.el("div", { class: "overlay-progress" }, [
      U.el("div", { class: "overlay-bar" }, [barFill]),
      counter,
      legacyCounterMarker,
    ]);
    // Track whether an AI action is in flight so close/X + Escape can
    // fire cancel_ai_action() before dismissing. Pro-only AI path, inert
    // in free (action_label is never a bare AI id here).
    var _aiActionInFlight = false;

    closeBtn.addEventListener("click", function () {
      if (_aiActionInFlight) { API.call("cancel_ai_action").catch(fail); }
      API.call("overlay_action", "close").catch(fail);
    });

    if (typeof document.addEventListener === "function") {
      document.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && !panel.classList.contains("hidden")) {
          if (_aiActionInFlight) { API.call("cancel_ai_action").catch(fail); }
          API.call("overlay_action", "close").catch(fail);
        }
      }, true);
    }
    var panel = U.el(
      "div",
      { class: "overlay-panel", testid: "overlay-panel" },
      [head, loadingEl, bodyEl, progress],
    );
    view.appendChild(panel);

    // Karaoke colour stops + fade — faithful port of overlay_paint.py
    // _word_appearance (PAST/FUTURE/PEAK RGB, smoothstep lerp, FADE_SECS).
    var PAST = [0x60, 0x65, 0x7a], FUTURE = [0xc8, 0xcd, 0xe0],
        PEAK = [0xff, 0xff, 0xff], FADE_SECS = 0.5;
    function smoothstep(t) {
      t = t < 0 ? 0 : t > 1 ? 1 : t;
      return t * t * (3 - 2 * t);
    }
    function lerpRGB(a, b, t) {
      t = smoothstep(t);
      return "rgb(" + Math.round(a[0]+(b[0]-a[0])*t) + ","
                    + Math.round(a[1]+(b[1]-a[1])*t) + ","
                    + Math.round(a[2]+(b[2]-a[2])*t) + ")";
    }
    function wordAppearance(i, cur, elapsed, w) {
      if (i === cur) return { color: "rgb(255,255,255)", cur: true };
      if (elapsed >= w.te) {
        var k = Math.max(0, 1 - (elapsed - w.te) / FADE_SECS);
        return { color: lerpRGB(PAST, PEAK, k), cur: false };
      }
      var k2 = Math.max(0, 1 - (w.ts - elapsed) / FADE_SECS);
      return { color: lerpRGB(FUTURE, PEAK, k2), cur: false };
    }

    var lastText = null;
    // Idle-aware polling: fast (~120ms) while active, slow (~2s) while idle.
    var _tickInterval = null;
    var _tickFast = null;
    var TICK_FAST_MS = 120;
    var TICK_SLOW_MS = 2000;

    function _setTickRate(fast) {
      if (_tickFast === fast) return;
      if (_tickInterval !== null) { clearInterval(_tickInterval); }
      _tickInterval = setInterval(tick, fast ? TICK_FAST_MS : TICK_SLOW_MS);
      _tickFast = fast;
    }

    function setVisible(vis) { panel.classList.toggle("hidden", !vis); }
    function tick() {
      API.call("engine_state")
        .then(function (s) {
          var st = s.overlay_state || "idle";
          document.body.setAttribute("data-overlay-state", st);
          var koff = parseInt(
            s.karaoke_offset_ms != null ? s.karaoke_offset_ms : 0, 10,
          ) / 1000.0;
          if (st === "idle") {
            setVisible(false);
            loadingEl.classList.add("hidden");
            bodyEl.textContent = "";
            barFill.style.width = "0%";
            lastText = null;
            _aiActionInFlight = false;
            _setTickRate(false);
            return;
          }
          _setTickRate(true);
          setVisible(true);
          dot.className = "overlay-dot" + (st === "reading" ? " reading"
            : st === "thinking" || st === "loading" ? " thinking" : "");
          label.textContent = (s.brand_name || "PipPal Pro")
            + (s.action_label ? "  ·  " + s.action_label : "");
          var isReading = st === "reading";
          var isNavigable = isReading || st === "thinking" || st === "loading";
          var prevDis = s.chunk_idx <= 0 || !isNavigable;
          var nextDis = s.chunk_total <= 1
            || s.chunk_idx >= s.chunk_total - 1 || !isNavigable;
          var pauseDis = !isReading;
          prevBtn.disabled = prevDis;
          prevBtn.classList.toggle("disabled", prevDis);
          nextBtn.disabled = nextDis;
          nextBtn.classList.toggle("disabled", nextDis);
          pauseBtn.disabled = pauseDis;
          pauseBtn.classList.toggle("disabled", pauseDis);
          replayBtn.disabled = !isReading;
          replayBtn.classList.toggle("disabled", !isReading);
          var pbSvgPath = pauseBtn.querySelector("svg path");
          var pbIconKey = s.is_paused ? "play" : "pause";
          if (pbSvgPath) pbSvgPath.setAttribute("d", ICONS[pbIconKey]);
          pauseBtn.setAttribute("data-icon", pbIconKey);
          if (st === "reading" && s.chunk_text) {
            _aiActionInFlight = false;
            loadingEl.classList.add("hidden");
            bodyEl.classList.remove("dimmed");
            if (s.chunk_text !== lastText) {
              lastText = s.chunk_text;
              bodyEl.innerHTML = "";
              s.words.forEach(function (w, i) {
                bodyEl.appendChild(U.el("span", {
                  class: "w", "data-i": String(i), text: w.word + " ",
                }));
              });
            }
            var elapsed = (s.elapsed || 0) - koff, cur = -1;
            s.words.forEach(function (w, i) { if (elapsed >= w.ts) cur = i; });
            var spans = bodyEl.querySelectorAll(".w");
            for (var i = 0; i < spans.length; i++) {
              var ap = wordAppearance(i, cur, elapsed, s.words[i]);
              var sp = spans[i];
              sp.style.color = ap.color;
              sp.className = "w" + (ap.cur ? " cur" : "");
            }
            var curSpan = bodyEl.querySelector(".cur");
            if (curSpan) { curSpan.scrollIntoView({ block: "nearest", inline: "nearest" }); }
            var prog = s.chunk_duration > 0
              ? Math.max(0, Math.min(1, (s.elapsed || 0) / s.chunk_duration)) : 0;
            barFill.style.width = (prog * 100).toFixed(1) + "%";
            counter.textContent = s.chunk_total > 1
              ? s.chunk_idx + 1 + "/" + s.chunk_total : "";
            legacyCounterMarker.textContent = counter.textContent;
          } else if (st === "thinking" || st === "loading") {
            // Pro-only AI path, inert in free (action_label never an AI id).
            var aiId = aiActionId(s.action_label);
            _aiActionInFlight = !!aiId;
            var explicit = !aiId && s.action_label && s.action_label !== "Loading…"
              ? s.action_label : null;
            var loadingLabel = aiId ? aiLoadingMessage(aiId)
              : explicit || currentLoadingMessage();
            lastText = null;
            loadingEl.classList.add("hidden");
            bodyEl.classList.remove("dimmed");
            var labelSpan = bodyEl.querySelector(".reader-loading-label");
            if (!labelSpan) {
              bodyEl.innerHTML =
                '<div class="reader-loading">' +
                '<div class="reader-loading-bar"></div>' +
                '<span class="reader-loading-label" aria-live="polite">' +
                escapeLoadingText(loadingLabel) +
                "</span>" +
                "</div>";
            } else if (labelSpan.textContent !== loadingLabel) {
              labelSpan.textContent = loadingLabel;
            }
            barFill.style.width = "0%";
          } else if (st === "done" && s.overlay_message) {
            lastText = null;
            loadingEl.classList.add("hidden");
            bodyEl.textContent = s.overlay_message;
          } else {
            lastText = null;
            loadingEl.classList.add("hidden");
            bodyEl.textContent = "";
            barFill.style.width = "0%";
          }
        })
        .catch(function () {});
    }
    // A2 — overlay kick: expose a guarded global so windows.py can call
    //   evaluate_js("window.__pippalOverlayKick && window.__pippalOverlayKick()")
    // immediately after show(). Forces fast tick without waiting for 2 s idle.
    window.__pippalOverlayKick = function () { _setTickRate(true); tick(); };

    _setTickRate(false);
    tick();
    return Promise.resolve();
  }

  function closeWin() { API.call("close_window").catch(function () {}); }

  // ------------------------------------------------------------------
  // Boot
  // ------------------------------------------------------------------
  var renderers = {
    settings: function () { wireFooter(); return renderSettings(); },
    onboarding: renderOnboarding,
    voices: renderVoiceManager,
    notices: renderNotices,
    overlay: renderOverlay,
  };
  (renderers[SURFACE] || renderers.settings)().then(function () {
    document.body.setAttribute("data-ready", SURFACE);
  }).catch(fail);
})();
