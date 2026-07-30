// S-1019 — one idempotency key per FORM FILL, not per submit.
//
// ★ The key is the client's statement that "this is the same submission as before". A key
// minted at submit time cannot make that statement — it says every submission is new, and
// the server, having been told exactly that, dutifully records two meals and two boluses.
// S-1016's duplicate check was correct and unreachable.
//
// It lives in localStorage next to the draft, and for the same reason: a reload mid-entry
// restores the draft, and a restored draft is the SAME submission. The key must survive
// with it or the crash-and-retry case — the one the draft exists for — double-logs.
//
// It rotates only after a CONFIRMED save. Rotating on any response would make a failed
// submit unsafe to retry; never rotating would make her second breakfast disappear.
(function (global) {
  "use strict";

  function mint() {
    if (global.crypto && global.crypto.randomUUID) return global.crypto.randomUUID();
    // Fallback for a browser without randomUUID. Date.now() alone repeats within a
    // millisecond, which is exactly the double-tap case, so it is mixed with randomness.
    return "k-" + Date.now() + "-" + Math.random().toString(36).slice(2, 10);
  }

  function current(store) {
    var key;
    try { key = localStorage.getItem(store); } catch (e) { key = null; }
    if (key) return key;
    key = mint();
    try { localStorage.setItem(store, key); } catch (e) { /* ignore */ }
    return key;
  }

  function rotate(store) {
    try { localStorage.removeItem(store); } catch (e) { /* ignore */ }
  }

  global.BGKey = { current: current, rotate: rotate };
})(window);
