// Meal-log form behaviour (S-301): favourite-populate, signed timing, a
// localStorage draft that survives a killed/failed submit, and submit.
// Adherence is the binding constraint: a repeat meal is a few taps.
(function () {
  "use strict";

  var form = document.getElementById("meal-form");
  if (!form) return;
  var DRAFT_KEY = "bgmarkov.meal-draft.v1";
  var toast = document.getElementById("toast");
  var timeInput = form.querySelector("[data-meal-time]");
  var chosen = form.querySelector("[data-chosen]");

  function setHidden(name, value) {
    var el = form.querySelector('[name="' + name + '"]');
    if (el) el.value = value;
  }

  function mealTypeFor(iso) {
    var h = iso ? new Date(iso).getHours() : new Date().getHours();
    if (h < 11) return "breakfast";
    if (h < 16) return "lunch";
    if (h < 21) return "dinner";
    return "snack";
  }

  // Pre-fill the time with now(), local, as an EDITABLE default (05b §3).
  // ★ S-1018: both live in reported-time.js now. `d.toISOString()` returns UTC, and the
  // popular fix — shifting the date by getTimezoneOffset() first — is the same bug in a
  // disguise and breaks across a DST boundary.
  var localIso = window.BGTime.localIso;
  var localNowIso = window.BGTime.localNowIso;

  // --- Draft persistence --------------------------------------------------
  function saveDraft() {
    var data = {};
    form.querySelectorAll("input, textarea").forEach(function (el) {
      if (el.name && el.type !== "hidden") data[el.name] = el.value;
    });
    try { localStorage.setItem(DRAFT_KEY, JSON.stringify(data)); } catch (e) { /* ignore */ }
  }

  function restoreDraft() {
    var raw;
    try { raw = localStorage.getItem(DRAFT_KEY); } catch (e) { return; }
    if (!raw) return;
    var data = JSON.parse(raw);
    Object.keys(data).forEach(function (name) {
      var el = form.querySelector('[name="' + name + '"]');
      if (el && el.type !== "hidden") el.value = data[name];
    });
  }

  function clearDraft() {
    try { localStorage.removeItem(DRAFT_KEY); } catch (e) { /* ignore */ }
  }

  // --- Chip groups (single-select) ---------------------------------------
  function selectInGroup(chip, groupSelector) {
    form.querySelectorAll(groupSelector).forEach(function (c) {
      c.setAttribute("aria-pressed", "false");
    });
    chip.setAttribute("aria-pressed", "true");
  }

  form.querySelectorAll("[data-favourite]").forEach(function (chip) {
    chip.addEventListener("click", function () {
      selectInGroup(chip, "[data-favourite]");
      setHidden("carbs_g", chip.dataset.carbs);
      setHidden("protein_g", chip.dataset.protein);
      setHidden("fat_g", chip.dataset.fat);
      setHidden("fiber_g", chip.dataset.fiber);
      setHidden("macro_confidence", "95");
      setHidden("meal_type", chip.dataset.mealType || mealTypeFor(timeInput.value));
      if (chosen) {
        chosen.hidden = false;
        chosen.textContent = "Selected: " + chip.dataset.name;
      }
      saveDraft();
    });
  });

  // The offset field holds the final SIGNED value. Presets write it directly;
  // the before/after buttons apply a sign to whatever magnitude is typed.
  var offsetField = form.querySelector("[data-offset-field]");
  var timingError = form.querySelector("[data-timing-error]");

  function clearTimingError() {
    if (timingError) timingError.hidden = true;
  }

  // Timing cannot be silently defaulted: "unset" is the EMPTY field, distinct
  // from a chosen 0 ("with food"). A preset/direction/typed value is a choice.
  function timingIsChosen() {
    return !!(offsetField && offsetField.value.trim() !== "");
  }

  form.querySelectorAll(".timing-preset").forEach(function (chip) {
    chip.addEventListener("click", function () {
      selectInGroup(chip, ".timing-preset");
      if (offsetField) offsetField.value = chip.dataset.offset;  // already signed
      clearTimingError();
      saveDraft();
    });
  });

  form.querySelectorAll("[data-dir]").forEach(function (chip) {
    chip.addEventListener("click", function () {
      selectInGroup(chip, "[data-dir]");
      if (offsetField) {
        var mag = Math.abs(parseInt(offsetField.value, 10) || 0);
        offsetField.value = chip.dataset.dir === "before" ? -mag : mag;
      }
      clearTimingError();
      saveDraft();
    });
  });
  if (offsetField) offsetField.addEventListener("input", clearTimingError);

  // --- Submit -------------------------------------------------------------
  function payload() {
    var iso = timeInput.value || localNowIso();
    // ★ S-1018 / ADR-8: sent as the LOCAL wall-clock time she typed. Converting it to a UTC
    // instant shifted every clinical timestamp by the browser's offset — 08:00 IST was
    // stored as 02:30 — while `meal_type`, decided below from the same local string, still
    // said "breakfast". The server now refuses anything carrying an offset.
    var reported = localIso(iso);
    return {
      idempotency_key: (window.crypto && crypto.randomUUID)
        ? crypto.randomUUID() : String(Date.now()),
      datetime: reported,
      meal_type: form.querySelector('[name="meal_type"]').value || mealTypeFor(iso),
      pre_bg: parseInt(form.querySelector('[name="pre_bg"]').value, 10),
      pre_bg_time: reported,
      carbs_g: parseFloat(form.querySelector('[name="carbs_g"]').value || "0"),
      protein_g: parseFloat(form.querySelector('[name="protein_g"]').value || "0"),
      fat_g: parseFloat(form.querySelector('[name="fat_g"]').value || "0"),
      fiber_g: parseFloat(form.querySelector('[name="fiber_g"]').value || "0"),
      macro_confidence: parseInt(form.querySelector('[name="macro_confidence"]').value || "95", 10),
      meal_bolus_units: parseFloat(form.querySelector('[name="meal_bolus_units"]').value || "0"),
      correction_bolus_units: parseFloat(
        form.querySelector('[name="correction_bolus_units"]').value || "0"),
      bolus_offset_min: parseInt(form.querySelector('[name="bolus_offset_min"]').value, 10),
      logged_by: "patient"
    };
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    // Timing cannot be skipped (REQ-003): block, prompt, and do NOT post.
    if (!timingIsChosen()) {
      if (timingError) {
        timingError.hidden = false;
        timingError.scrollIntoView({ block: "nearest" });
      }
      if (offsetField) offsetField.focus();
      return;
    }
    fetch(form.action, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload())
    }).then(function (r) {
      if (!r.ok) throw new Error("submit failed");
      return r.json();
    }).then(function (body) {
      clearDraft();  // only after a confirmed save
      toast.hidden = false;
      toast.textContent = "✓ " + (body.message || "Logged.");
      toast.scrollIntoView({ block: "nearest" });
    }).catch(function () {
      toast.hidden = false;
      toast.textContent = "Could not save — your entry is kept; try again.";
    });
  });

  // --- Init ---------------------------------------------------------------
  form.addEventListener("input", saveDraft);
  restoreDraft();
  if (timeInput && !timeInput.value) timeInput.value = localNowIso();
})();
