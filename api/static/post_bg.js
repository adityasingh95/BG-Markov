// Post-meal reading (S-303): one number, one REPORTED time. < 15 s.
// Feedback is non-judgemental (05b §4): "a bit late, that's fine", never a scold.
(function () {
  "use strict";

  var form = document.getElementById("post-bg-form");
  if (!form) return;
  var toast = document.getElementById("toast");
  var timeInput = form.querySelector("[data-post-bg-time]");

  // Pre-fill the reading time with the EXPECTED time (mealtime + 120), editable.
  if (timeInput && !timeInput.value) {
    timeInput.value = form.dataset.expectedReading || "";
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var iso = timeInput.value;
    if (!iso) {
      toast.hidden = false;
      toast.textContent = "When did you take this reading? Please add the time.";
      return;
    }
    var body = {
      post_bg: parseInt(form.querySelector('[name="post_bg"]').value, 10),
      post_bg_time: new Date(iso).toISOString(),
      hypo_treatment: !!form.querySelector("[data-hypo]").checked,
      snack_during_window: false
    };
    var grams = form.querySelector('[name="hypo_treatment_g"]').value;
    if (grams !== "") body.hypo_treatment_g = parseFloat(grams);

    fetch(form.action, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    }).then(function (r) {
      if (!r.ok) throw new Error("save failed");
      return r.json();
    }).then(function (res) {
      toast.hidden = false;
      if (res.is_valid) {
        toast.textContent = "✓ Saved — " + res.elapsed_min + " min after your meal.";
      } else if ((res.exclusion_reasons || []).indexOf("outside_window") !== -1) {
        toast.textContent = "✓ Saved — a bit outside the 2-hour window, that's fine.";
      } else {
        toast.textContent = "✓ Saved.";
      }
      toast.scrollIntoView({ block: "nearest" });
    }).catch(function () {
      toast.hidden = false;
      toast.textContent = "Could not save — please try again.";
    });
  });
})();
