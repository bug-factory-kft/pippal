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

  function renderSettings() {
    return Promise.all([
      API.call("get_config"),
      API.call("get_defaults"),
      API.call("get_engines"),
      API.call("get_installed_voices"),
      API.call("get_hotkey_actions"),
      API.call("context_menu_status"),
      API.call("about_info"),
    ]).then(function (res) {
      var cfg = res[0], defs = res[1], engines = res[2], voices = res[3];
      var hotkeys = res[4], ctxStatus = res[5], about = res[6];
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
        if (!close) return renderSettings();
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
  // VOICE MANAGER (voice_manager.py parity).
  // ------------------------------------------------------------------
  var vmState = { all: [], lang: "__all__", quality: "Any", status: "Any", q: "" };

  function renderVoiceManager() {
    return API.call("get_voice_catalogue").then(function (cat) {
      vmState.all = cat.voices;
      document.getElementById("brand-name").textContent = "Voices";
      view.innerHTML = "";
      footer.classList.add("hidden");

      var langOpts = [{ value: "__all__", label: "All languages" }].concat(
        cat.languages.map(function (l) { return { value: l.code, label: l.name }; }));
      var langSel = U.select("vm-language", langOpts, vmState.lang);
      var qualSel = U.select("vm-quality",
        ["Any", "high", "medium", "low", "x_low"].map(function (q) {
          return { value: q, label: q };
        }), vmState.quality);
      var statSel = U.select("vm-status",
        ["Any", "Installed", "Not installed"].map(function (s) {
          return { value: s, label: s };
        }), vmState.status);
      var searchInp = U.el("input", { type: "text", testid: "vm-search",
        placeholder: "" });
      searchInp.classList.add("grow");

      langSel.addEventListener("change", function () {
        vmState.lang = langSel.value; refreshRows();
      });
      qualSel.addEventListener("change", function () {
        vmState.quality = qualSel.value; refreshRows();
      });
      statSel.addEventListener("change", function () {
        vmState.status = statSel.value; refreshRows();
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
          U.el("label", { class: "field-label", text: "Language",
            style: "flex:0 0 80px;width:80px" }), langSel,
          U.el("label", { class: "field-label", text: "Quality",
            style: "flex:0 0 64px;width:64px" }), qualSel,
          U.el("label", { class: "field-label", text: "Status",
            style: "flex:0 0 56px;width:56px" }), statSel,
        ]),
        U.el("div", { class: "row" }, [
          U.el("label", { class: "field-label", text: "Search",
            style: "flex:0 0 80px;width:80px" }), searchInp,
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
          if (vmState.quality !== "Any" && v.quality !== vmState.quality) return;
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
          rowsWrap.appendChild(U.el("div", { class: "empty", testid: "vm-empty",
            text: "No voices match. Clear the filter to see everything." }));
        }
      }
      refreshRows();
    });
  }

  function voiceRow(v, onChanged) {
    var statusEl = U.el("span", { class: "vstatus" + (v.installed ? " ok" : ""),
      testid: "vm-status-" + v.id,
      text: v.installed ? "✓ installed" : "" });
    var btn = U.el("button", {
      testid: "vm-action-" + v.id,
      text: v.installed ? "Remove" : "Install",
      class: v.installed ? "danger" : "",
    });
    function doRemove() {
      btn.disabled = true;
      statusEl.textContent = "removing…";
      API.call("remove_voice", v.id).then(function () {
        onChanged();
      }).catch(function (e) { btn.disabled = false; fail(e); });
    }
    function doInstall() {
      btn.disabled = true;
      statusEl.textContent = "downloading…";
      statusEl.className = "vstatus";
      API.call("install_voice", v.id).then(function () {
        onChanged();
      }).catch(function (e) {
        statusEl.textContent = "failed";
        statusEl.className = "vstatus err";
        btn.disabled = false;
        fail(e);
      });
    }
    btn.addEventListener("click", function () {
      if (v.installed) {
        // Tk parity: messagebox.askyesno("Remove voice", "Remove
        // {label}?") — the deletion must NOT run until the user accepts
        // the modal. Cancel leaves the voice on disk untouched.
        confirmDialog("Remove voice", "Remove " + v.label + "?")
          .then(function (ok) { if (ok) doRemove(); });
      } else {
        doInstall();
      }
    });
    return U.el("div", { class: "card" }, [
      U.el("div", { class: "vrow" }, [
        U.el("div", { class: "vmeta" }, [
          U.el("div", { class: "vname", text: v.label }),
          U.el("div", { class: "vsub", text: "id: " + v.id + "   ·   " + v.quality }),
        ]),
        statusEl, btn,
      ]),
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

  // Playful loading messages (#6) -- whimsical, fake-technical lines
  // ported from Pro's overlay.js. They rotate while the overlay is in
  // the loading/thinking state.
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
  var LOADING_ROTATE_MS = 1800;
  var loadingMsgBase = Math.floor(Math.random() * LOADING_MESSAGES.length);
  function currentLoadingMessage() {
    var step = Math.floor(Date.now() / LOADING_ROTATE_MS);
    var idx = (loadingMsgBase + step) % LOADING_MESSAGES.length;
    return LOADING_MESSAGES[idx];
  }

  // ------------------------------------------------------------------
  // READER OVERLAY panel (overlay.py / overlay_paint.py parity).
  // ------------------------------------------------------------------
  function renderOverlay() {
    document.body.classList.add("overlay-mode");
    document.getElementById("titlebar").classList.add("hidden");
    footer.classList.add("hidden");
    view.style.padding = "0";
    view.innerHTML = "";

    var dot = U.el("span", { class: "overlay-dot", testid: "overlay-dot" });
    var label = U.el("span", { class: "ohlabel", testid: "overlay-label",
      text: "PipPal" });
    var closeBtn = U.el("button", { class: "overlay-close",
      testid: "overlay-close", html: "&#x2715;" });
    var head = U.el("div", { class: "overlay-head" }, [
      U.el("img", { src: "assets/pippal_icon.png" }), dot, label, closeBtn,
    ]);
    var pausedChip = U.el("div", { class: "overlay-paused hidden",
      testid: "overlay-paused", text: "paused" });
    var bodyEl = U.el("div", { class: "overlay-body", testid: "overlay-text" });
    var barFill = U.el("div");
    var counter = U.el("span", { class: "overlay-counter",
      testid: "overlay-counter", text: "" });
    function obtn(tag, glyph) {
      var b = U.el("button", { class: "obtn", testid: "overlay-" + tag,
        html: glyph });
      b.addEventListener("click", function () {
        API.call("overlay_action", tag).catch(fail);
      });
      return b;
    }
    var progress = U.el("div", { class: "overlay-progress" }, [
      obtn("prev", "&#x23ee;"), obtn("replay", "&#x27f2;"),
      obtn("next", "&#x23ed;"),
      U.el("div", { class: "overlay-bar" }, [barFill]),
      counter,
    ]);
    closeBtn.addEventListener("click", function () {
      API.call("overlay_action", "close").catch(fail);
    });
    var panel = U.el("div", { class: "overlay-panel", testid: "overlay-panel" }, [
      head, pausedChip, bodyEl, progress,
    ]);
    view.appendChild(panel);

    // ---- Drag-to-reposition (parity with Tk overlay's right-drag) ----
    // Tk binds <ButtonPress-3>/<B3-Motion> to move the frameless panel.
    // The web panel is a centred block; mirror that with a right-button
    // drag that offsets it via a transform. (The desktop pywebview frame
    // additionally has CSS `app-region: drag`; this covers served mode.)
    var drag = { active: false, sx: 0, sy: 0, ox: 0, oy: 0 };
    panel.addEventListener("contextmenu", function (e) { e.preventDefault(); });
    panel.addEventListener("mousedown", function (e) {
      if (e.button !== 2) return;            // right button only (Tk Button-3)
      drag.active = true;
      drag.sx = e.clientX; drag.sy = e.clientY;
      panel.setAttribute("data-dragging", "1");
      e.preventDefault();
    });
    window.addEventListener("mousemove", function (e) {
      if (!drag.active) return;
      var nx = drag.ox + (e.clientX - drag.sx);
      var ny = drag.oy + (e.clientY - drag.sy);
      panel.style.transform = "translate(" + nx + "px," + ny + "px)";
      panel.setAttribute("data-offset", nx + "," + ny);
    });
    window.addEventListener("mouseup", function (e) {
      if (!drag.active || e.button !== 2) return;
      drag.active = false;
      drag.ox += (e.clientX - drag.sx);
      drag.oy += (e.clientY - drag.sy);
      panel.removeAttribute("data-dragging");
    });

    // Karaoke colour stops + fade — a faithful port of overlay_paint.py's
    // _word_appearance (PAST/FUTURE/PEAK RGB, smoothstep lerp, FADE_SECS).
    var PAST = [0x60, 0x65, 0x7a], FUTURE = [0xc8, 0xcd, 0xe0],
        PEAK = [0xff, 0xff, 0xff], FADE_SECS = 0.50;
    function smoothstep(t) { t = t < 0 ? 0 : (t > 1 ? 1 : t); return t * t * (3 - 2 * t); }
    function lerpRGB(a, b, t) {
      t = smoothstep(t);
      return "rgb(" + Math.round(a[0] + (b[0] - a[0]) * t) + ","
                    + Math.round(a[1] + (b[1] - a[1]) * t) + ","
                    + Math.round(a[2] + (b[2] - a[2]) * t) + ")";
    }
    // Mirrors overlay_paint._word_appearance: the cursor word is pure
    // PEAK + bold; words before bleed PAST->PEAK over FADE_SECS after
    // their te; words ahead bleed FUTURE->PEAK over FADE_SECS before ts.
    function wordAppearance(i, cur, elapsed, w) {
      if (i === cur) return { color: "rgb(255,255,255)", cur: true };
      if (elapsed >= w.te) {
        var k = Math.max(0, 1 - (elapsed - w.te) / FADE_SECS);
        return { color: lerpRGB(PAST, PEAK, k), cur: false };
      }
      var k2 = Math.max(0, 1 - (w.ts - elapsed) / FADE_SECS);
      return { color: lerpRGB(FUTURE, PEAK, k2), cur: false };
    }

    // Poll the engine snapshot and re-render the karaoke line; this is
    // the web analogue of overlay.py's tk.after animation loop. The
    // panel is hidden when the engine state is `idle` (the web analogue
    // of the Tk overlay's win.withdraw()) — so the backend's real
    // auto-hide timer (WebOverlay._on_hide_timeout) visibly hides it.
    var lastText = null;
    function setVisible(vis) {
      panel.classList.toggle("hidden", !vis);
    }
    function tick() {
      API.call("engine_state").then(function (s) {
        var st = s.overlay_state || "idle";
        // Expose state for E2E + so auto-hide is observable from the DOM.
        document.body.setAttribute("data-overlay-state", st);
        // Karaoke offset: positive = highlight waits, negative = leads
        // (parity with the Tk karaoke_offset_ms config; the Tk overlay
        // applies it as the chunk start offset_s, here we shift elapsed).
        var koff = parseInt(s.karaoke_offset_ms != null
          ? s.karaoke_offset_ms : 0, 10) / 1000.0;
        if (st === "idle") {
          // Auto-hidden (or never started): panel disappears like
          // win.withdraw(). Nothing else to paint.
          setVisible(false);
          bodyEl.textContent = "";
          barFill.style.width = "0%";
          lastText = null;
          return;
        }
        setVisible(true);
        dot.className = "overlay-dot" + (st === "reading" ? " reading"
          : st === "thinking" ? " thinking" : "");
        label.textContent = (s.brand_name || "PipPal")
          + (s.action_label ? "  ·  " + s.action_label : "");
        pausedChip.classList.toggle("hidden", !(s.is_paused && st === "reading"));
        if (st === "reading" && s.chunk_text) {
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
          var prog = s.chunk_duration > 0
            ? Math.max(0, Math.min(1, (s.elapsed || 0) / s.chunk_duration)) : 0;
          barFill.style.width = (prog * 100).toFixed(1) + "%";
          counter.textContent = s.chunk_total > 1
            ? (s.chunk_idx + 1) + "/" + s.chunk_total : "";
        } else if (st === "thinking") {
          bodyEl.textContent = s.action_label || currentLoadingMessage();
          barFill.style.width = "0%";
        } else if (st === "done" && s.overlay_message) {
          bodyEl.textContent = s.overlay_message;
        } else {
          bodyEl.textContent = "";
          barFill.style.width = "0%";
          lastText = null;
        }
      }).catch(function () {});
    }
    tick();
    setInterval(tick, 120);
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
