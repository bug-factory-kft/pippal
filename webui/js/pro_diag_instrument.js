/* pro_diag_instrument.js — Pro-owned frontend diagnostics instrumentation.
 *
 * This file MUST be loaded AFTER api.js.  It wraps window.PipPalAPI.call
 * so that every bridge invocation fires a fire-and-forget diag_js breadcrumb
 * (invoke / resolve / reject) and installs global error handlers for
 * unhandledrejection and window.onerror.
 *
 * Design constraints:
 *   - api.js is byte-identical to the public core and MUST NOT be modified.
 *     All Pro-specific instrumentation lives here.
 *   - The wrapper is transparent: it returns the EXACT same Promise that the
 *     original PipPalAPI.call returned; calling semantics are unchanged.
 *   - Guard: when method === "diag_js" the wrapper is skipped entirely to
 *     prevent infinite recursion.
 *   - Every diag_js call is fire-and-forget; any error it throws is swallowed
 *     so instrumentation can NEVER break a real call.
 *   - Privacy: only the method name, ok flag, and a short (<=120 char)
 *     error type/message are emitted — never arguments, read text, or any
 *     user content.
 *   - The diag_js backend already no-ops when diagnostics are off, so no
 *     front-end level-check is needed here.
 */
(function () {
  "use strict";

  var _api = window.PipPalAPI;
  if (!_api || typeof _api.call !== "function") {
    // api.js not yet loaded or not present — nothing to instrument.
    return;
  }

  var _origCall = _api.call.bind(_api);

  // ---------------------------------------------------------------------------
  // Helper: send a fire-and-forget diag_js breadcrumb.  Never throws.
  // ---------------------------------------------------------------------------

  function _diag(event, method, ok, detail) {
    try {
      var args = [event];
      if (method !== null && method !== undefined) args.push(method);
      else args.push(null);
      if (ok !== null && ok !== undefined) args.push(ok);
      else args.push(null);
      if (detail !== null && detail !== undefined) args.push(String(detail).slice(0, 120));
      // Use the ORIGINAL call so we bypass our wrapper.
      _origCall("diag_js", event, method !== undefined ? method : null,
                ok !== undefined ? ok : null,
                detail !== undefined ? String(detail).slice(0, 120) : null);
    } catch (_e) {
      // Instrumentation must never surface errors to the caller.
    }
  }

  // ---------------------------------------------------------------------------
  // Wrap PipPalAPI.call
  // ---------------------------------------------------------------------------

  _api.call = function (method) {
    var args = Array.prototype.slice.call(arguments);

    // Guard: never instrument the diag_js call itself (no recursion).
    if (method === "diag_js") {
      return _origCall.apply(null, args);
    }

    // Fire "invoke" breadcrumb — fire-and-forget, swallow errors.
    try { _diag("invoke", method, null, null); } catch (_e) {}

    var result;
    try {
      result = _origCall.apply(null, args);
    } catch (syncErr) {
      // Synchronous throw from the original call (should not happen,
      // but handle defensively).
      try { _diag("reject", method, false, (syncErr && syncErr.name) ? syncErr.name : "Error"); } catch (_e) {}
      throw syncErr;
    }

    // If result is a Promise (or thenable), attach OBSERVER callbacks.
    // IMPORTANT: we attach to a SIDE-CHAIN off the original promise so the
    // original promise's rejection still propagates unmodified to the real
    // caller's .catch().  The observer chain swallows its own rejection with
    // a no-op handler to avoid an unhandled-rejection warning on the side
    // chain (the real rejection already surfaces on the original chain).
    if (result && typeof result.then === "function") {
      result.then(
        function (r) {
          try { _diag("resolve", method, !!(r && r.ok !== false), null); } catch (_e) {}
          // Return value is irrelevant — side-chain, not the real chain.
        },
        function (err) {
          var shortErr = (err && err.name) ? err.name : "Error";
          if (err && err.message) {
            shortErr = (err.name || "Error") + ":" + String(err.message).slice(0, 80);
          }
          try { _diag("reject", method, false, shortErr); } catch (_e) {}
          // Do NOT re-throw here: this side-chain must resolve (not reject) so
          // the side-chain promise is handled.  The REAL rejection travels on
          // the original `result` promise which is returned to the caller below.
        }
      );
    }

    // Return the ORIGINAL promise/value unchanged so callers are unaffected.
    return result;
  };

  // ---------------------------------------------------------------------------
  // Global error handlers
  // ---------------------------------------------------------------------------

  window.addEventListener("unhandledrejection", function (evt) {
    try {
      var reason = evt && evt.reason;
      var detail = reason
        ? ((reason.name || "Error") + ":" + String(reason.message || "").slice(0, 80))
        : "UnhandledRejection";
      _diag("unhandledrejection", null, false, detail);
    } catch (_e) {}
  });

  window.onerror = (function (_prev) {
    return function (msg, src, line, col, err) {
      try {
        var detail = err
          ? ((err.name || "Error") + ":" + String(err.message || "").slice(0, 80))
          : String(msg || "error").slice(0, 100);
        _diag("error", null, false, detail);
      } catch (_e) {}
      if (typeof _prev === "function") {
        return _prev.apply(this, arguments);
      }
      return false;
    };
  }(window.onerror));

}());
