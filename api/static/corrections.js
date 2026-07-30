// Correction-only event (S-306): the clean ISF signal. Two-phase — log now, and
// if no food is coming, a +4 h follow-up BG. datetime is REPORTED (ADR-8).
(function () {
  "use strict";

  var form = document.getElementById("correction-form");
  if (!form) return;
  var toast = document.getElementById("toast");
  var timeInput = form.querySelector("[data-correction-time]");
  var KEY_STORE = "bgmarkov.correction-key.v1";  // ★ S-1019: a correction is a bolus too

  // The key rotates when the next fill BEGINS, not when a save returns — see app.js for
  // why. This form keeps no draft, so a fresh page load is itself a new fill: the first
  // edit after load, and the first edit after a save, each start one.
  var rotateOnNextEdit = true;
  form.addEventListener("input", function () {
    if (!rotateOnNextEdit) return;
    rotateOnNextEdit = false;
    window.BGKey.rotate(KEY_STORE);
  });

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var iso = timeInput.value;
    if (!iso) {
      toast.hidden = false;
      toast.textContent = "When did you take the correction? Please add the time.";
      return;
    }
    var food = form.querySelector('[name="food_in_window"]:checked');
    if (!food) {
      toast.hidden = false;
      toast.textContent = "Will you be eating in the next 4 hours? Please choose.";
      return;
    }
    var body = {
      idempotency_key: window.BGKey.current(KEY_STORE),
      datetime: window.BGTime.localIso(iso),  // ★ S-1018: local, never UTC
      bg_before: parseInt(form.querySelector('[name="bg_before"]').value, 10),
      units: parseFloat(form.querySelector('[name="units"]').value),
      food_in_window: food.value === "yes"
    };

    var button = form.querySelector('button[type="submit"]');
    if (button) button.disabled = true;

    fetch(form.action, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    }).then(function (r) {
      if (!r.ok) throw new Error("save failed");
      return r.json();
    }).then(function (res) {
      rotateOnNextEdit = true;
      toast.hidden = false;
      toast.textContent = "✓ " + (res.message || "Saved.");
      toast.scrollIntoView({ block: "nearest" });
    }).catch(function () {
      toast.hidden = false;
      toast.textContent = "Could not save — please try again.";
    }).then(function () {
      if (button) button.disabled = false;
    });
  });
})();
