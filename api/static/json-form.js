// S-1020 — the shared submitter for forms that post JSON to /api/.
//
// ★ `basal.html`, `profile.html` and `operator_shadow.html` were plain HTML forms posting
// natively to JSON endpoints. The browser sends application/x-www-form-urlencoded, FastAPI
// returns 422, and the browser NAVIGATES to it — so she leaves the app and lands on a raw
// JSON blob. Neither the daily Tresiba dose, nor the clinical constants, nor the kill
// switch could be operated from a browser at all.
//
// One shared submitter rather than three more bespoke scripts: these three forms do nothing
// special. The bespoke handlers stay bespoke because they do real work — draft persistence,
// timing validation, hypo fields — that a generic serialiser should not try to absorb.
//
// Field types are DECLARED (`data-type="number"` / `"bool"`), never guessed. Guessing from
// the value means "26" becomes a number and "26 " does not, and a silently-wrong type at a
// clinical endpoint is exactly the class of failure this project keeps finding.
(function () {
  "use strict";

  var FAILURE = "Could not save — please try again.";

  function coerce(input) {
    var kind = input.getAttribute("data-type");
    var value = input.value;
    if (kind === "number") return value === "" ? null : parseFloat(value);
    if (kind === "bool") return value === "true" || value === "on" || value === "1";
    return value;
  }

  function bodyOf(form) {
    var body = {};
    form.querySelectorAll("input[name], select[name], textarea[name]").forEach(function (el) {
      if (el.type === "radio" && !el.checked) return;
      if (el.type === "checkbox") { body[el.name] = el.checked; return; }
      body[el.name] = coerce(el);
    });
    return body;
  }

  function describe(res, form) {
    var message = res && res.message ? res.message : (form.dataset.savedMessage || "Saved.");
    // ★ DL-048: "a validation result nobody can see is not a warning." The profile
    // endpoint has returned `flags` since S-1010 and the page threw them away.
    if (res && res.flags && res.flags.length) {
      message += " — flagged: " + res.flags.join("; ");
    }
    return "✓ " + message;
  }

  document.querySelectorAll("form[data-json-form]").forEach(function (form) {
    var toast = document.getElementById("toast");

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (!form.reportValidity()) return;

      var button = form.querySelector('button[type="submit"]');
      if (button) button.disabled = true;

      fetch(form.action, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(bodyOf(form))
      }).then(function (r) {
        if (!r.ok) throw new Error("save failed");
        return r.json();
      }).then(function (res) {
        if (toast) {
          toast.hidden = false;
          toast.textContent = describe(res, form);
          toast.scrollIntoView({ block: "nearest" });
        }
      }).catch(function () {
        if (toast) {
          toast.hidden = false;
          toast.textContent = FAILURE;
        }
      }).then(function () {
        if (button) button.disabled = false;
      });
    });
  });
})();
