/* api.js — single transport seam for the PipPal web UI.
 *
 * The exact same static frontend runs in two modes:
 *
 *   1. Desktop: pywebview injects `window.pywebview.api`, a Python
 *      bridge object whose methods return Promises. Real backend.
 *
 *   2. Served / E2E: the bridge is also exposed over a localhost HTTP
 *      JSON endpoint (`/bridge`) by web_ui/server.py. When pywebview
 *      is absent we POST {method, args} there. Playwright drives this
 *      mode against the real backend with real DOM events.
 *
 * Every backend call goes through PipPalAPI.call(); the UI never
 * branches on transport.
 */
(function () {
  "use strict";

  function httpCall(method, args) {
    return fetch("/bridge", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ method: method, args: args || [] }),
    }).then(function (r) {
      if (!r.ok) {
        return r.text().then(function (t) {
          throw new Error("bridge " + r.status + ": " + t);
        });
      }
      return r.json();
    }).then(function (payload) {
      if (payload && payload.__error__) {
        throw new Error(payload.__error__);
      }
      return payload;
    });
  }

  function bridgeReady() {
    return new Promise(function (resolve) {
      if (window.pywebview && window.pywebview.api) {
        resolve(true);
        return;
      }
      // pywebview fires `pywebviewready` once the bridge is injected.
      var done = false;
      function finish(hasBridge) {
        if (done) return;
        done = true;
        resolve(hasBridge);
      }
      window.addEventListener("pywebviewready", function () {
        finish(!!(window.pywebview && window.pywebview.api));
      });
      // Served mode never fires the event — fall back to HTTP fast.
      setTimeout(function () {
        finish(!!(window.pywebview && window.pywebview.api));
      }, 600);
    });
  }

  var readyPromise = bridgeReady();

  var PipPalAPI = {
    /** Call a bridge method by name; returns a Promise of its result. */
    call: function (method) {
      var args = Array.prototype.slice.call(arguments, 1);
      return readyPromise.then(function (hasBridge) {
        if (hasBridge && window.pywebview && window.pywebview.api &&
            typeof window.pywebview.api[method] === "function") {
          return window.pywebview.api[method].apply(window.pywebview.api, args);
        }
        return httpCall(method, args);
      });
    },
  };

  window.PipPalAPI = PipPalAPI;
})();
