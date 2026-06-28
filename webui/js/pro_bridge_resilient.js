/* pro_bridge_resilient.js — Pro-owned cold-create bridge resilience.
 *
 * HARD CONSTRAINT H1: api.js is byte-identical to the public core and MUST
 * NOT be edited.  All Pro-specific hardening lives here.
 *
 * Problem: on cold create (first launch / onboarding) there is a narrow
 * post-load warmup window where window.pywebview.api is chosen as the
 * transport by api.js but the bridge may not yet be fully initialised,
 * causing a transient reject on the very first call.  This produces the
 * "blank/empty window" symptom (page loaded but first get_config reject
 * leaves DOM empty).
 *
 * Solution: wrap PipPalAPI.call so that when:
 *   1. The call was dispatched within WARMUP_MS ms of page load (narrowly
 *      post-load warmup window), AND
 *   2. The underlying call rejects (transient bridge error), AND
 *   3. The method is read-only / idempotent (safe to retry), AND
 *   4. window.pywebview.api was the chosen transport (not already HTTP),
 * ... we retry ONCE via the HTTP /bridge fallback (same payload shape as
 * api.js: POST {method, args}).  The Promise contract is transparent
 * (same resolve/reject shape to callers).
 *
 * This file MUST be loaded AFTER api.js AND pro_diag_instrument.js (so it
 * wraps the already-instrumented call).
 */
(function () {
  "use strict";

  var _api = window.PipPalAPI;
  if (!_api || typeof _api.call !== "function") {
    return; // api.js not yet loaded — nothing to wrap.
  }

  // Warmup window: retry is only active for the first WARMUP_MS after load.
  var WARMUP_MS = 3000;
  var _loadTime = Date.now();

  // Read-only / idempotent methods safe to retry once.
  var RETRY_SAFE = {
    get_config: true,
    get_queue: true,
    get_voice_catalogue: true,
    get_hotkey_actions: true,
    get_pronunciation_rules: true,
    get_onboarding_state: true,
    get_release_history: true,
    get_kokoro_state: true,
    get_crash_prompt: true,
    get_ctx_menu_status: true,
    get_overlay_state: true,
    get_mood_list: true,
    get_recent_docs: true,
  };

  // HTTP fallback that mirrors api.js's httpCall exactly.
  function _httpFallback(method, args) {
    return fetch("/bridge", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ method: method, args: args || [] }),
    }).then(function (r) {
      if (!r.ok) {
        return r.text().then(function (t) {
          throw new Error("bridge-fallback " + r.status + ": " + t);
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

  var _origCall = _api.call.bind(_api);

  _api.call = function (method) {
    var args = Array.prototype.slice.call(arguments, 1);

    var withinWarmup = (Date.now() - _loadTime) < WARMUP_MS;
    var isSafe = !!RETRY_SAFE[method];
    var hasPyBridge = !!(window.pywebview && window.pywebview.api);

    // Only add retry logic when inside warmup + safe method + pywebview bridge.
    if (withinWarmup && isSafe && hasPyBridge) {
      return _origCall.apply(null, [method].concat(args)).catch(function (err) {
        // Transient bridge reject during warmup: retry once via HTTP fallback.
        return _httpFallback(method, args);
      });
    }

    return _origCall.apply(null, [method].concat(args));
  };

}());
