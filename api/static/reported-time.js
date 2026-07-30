// S-1018 / ADR-8 — the ONE place a reported clinical time becomes a wire value.
//
// ★ A `datetime-local` input's `.value` is ALREADY a local wall-clock ISO string:
// "2026-07-30T11:20". That is exactly what the server wants, and passing it through
// `new Date(value).toISOString()` converts it to a UTC instant — shifting every clinical
// timestamp by the browser's offset. On a phone in Asia/Kolkata a breakfast typed as 08:00
// was stored as 02:30, silently, with `meal_type` still saying "breakfast".
//
// The conversion was pure loss. There is nothing to convert: she reports wall-clock times.
// The server now refuses anything carrying an offset (core.timestamps.require_naive), so a
// regression here is a 422 rather than a corrupted row.
(function (global) {
  "use strict";

  function pad(n) { return (n < 10 ? "0" : "") + n; }

  // Normalise a datetime-local value to "YYYY-MM-DDTHH:MM:SS". No timezone, ever.
  function localIso(value) {
    if (!value) return "";
    return value.length === 16 ? value + ":00" : value;
  }

  // "Now", as a LOCAL wall-clock string for pre-filling a field she can edit.
  // Built field by field on purpose: the shorter `d.toISOString()` returns UTC, and the
  // popular fix — shifting the date by getTimezoneOffset() first — is the same bug wearing
  // a disguise, and breaks across a DST boundary.
  function localNowIso() {
    var d = new Date();
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) +
      "T" + pad(d.getHours()) + ":" + pad(d.getMinutes());
  }

  global.BGTime = { localIso: localIso, localNowIso: localNowIso };
})(window);
