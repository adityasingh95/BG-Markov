# Durability Drill Log

*Owner: BA. `06 §5` / REQ-051: a restore drill is run in **month one, before
there is real data to lose**, and re-run monthly. **An untested backup is not a
backup.** This file is the evidence that the restore actually works — the audit
looks here for the executed date, not just that the code exists.*

Each entry records: date run · what was exercised · result · who/where.

---

## 2026-07-15 — initial drill (S-304), before real data exists ✅ PASS

**Run by:** operator agent, in the build environment, on a real sample DB (the
schema from S-201 with 12 `meal_event` rows + 1 `patient_profile` version — a
stand-in for pre-collection data, exactly the "before there is data to lose"
window REQ-051 requires).

**Commands (all three durability mechanisms exercised):**
```
BGAPP_DB_URL=sqlite:///…/bgapp/app.db  BGAPP_BACKUP_DIR=…/backups
python -m cli backup          # online snapshot -> backups/snap.db
python -m cli export          # CSV per table   -> backups/*.csv
python -m cli restore-drill   # restore + verify
```

**Result:**
```
backup ok -> …/backups/snap.db
exported 9 table(s) -> …/backups
restore-drill: ok=True integrity_ok=True identical=True
  tables={audit_log:0, basal_log:0, bolus_log:0, correction_event:0, dish:0,
          meal_event:12, model_artifact:0, patient_profile:1, prediction_log:0}
exit=0
```

**Verified:**
- `PRAGMA integrity_check == ok` on the restored DB.
- Restored file **byte-identical** to the snapshot; source **data dump identical**
  to the restored dump (`sha256` of the canonical `.dump`).
- All 12 meals + the profile version survived; 9 per-table CSVs written with
  headers.
- The live-DB-in-a-synced-folder guard (`SyncedFolderError`) is covered by
  `tests/safety/test_backup_restore.py` and enforced by `cli.backup`.

**Conclusion:** the restore path works end-to-end. S-304's ★ execution
requirement is satisfied.

**Next drill due:** monthly (operator), and again immediately before the first
real logging goes live. Update this log each time.

---

## 2026-07-16 — verification re-run (audit N4) ✅ PASS · captured transcript

**Why:** audit 2026-07-16-01 (N4) asked for a **captured transcript** rather than
typed prose, as stronger evidence for a `[SAFETY]` "run for real" story. Re-run on
the current (post-S-305) schema — now **10 tables** (adds `hypo_rescue_log`).

**Captured transcript (real stdout):**
```
=== TRANSCRIPT START (2026-07-16T05:25:35Z) ===
$ python -m cli backup
backup ok -> …/drill-2026-07-16/backups/snap.db
$ python -m cli export
exported 10 table(s) -> …/drill-2026-07-16/backups
$ python -m cli restore-drill
restore-drill: ok=True integrity_ok=True identical=True tables={'audit_log': 0,
  'basal_log': 0, 'bolus_log': 0, 'correction_event': 0, 'dish': 0,
  'hypo_rescue_log': 0, 'meal_event': 12, 'model_artifact': 0,
  'patient_profile': 1, 'prediction_log': 0}
exit=0
=== ls backups ===
audit_log.csv  basal_log.csv  bolus_log.csv  correction_event.csv  dish.csv
hypo_rescue_log.csv  meal_event.csv  model_artifact.csv  patient_profile.csv
prediction_log.csv  snap.db
=== TRANSCRIPT END ===
```

**Result:** `ok=True integrity_ok=True identical=True`; 12 meals + 1 profile
version survived; 10 per-table CSVs written. Corroborates the 2026-07-15 entry
(same mechanism; the table count rose from 9→10 exactly because S-305 added
`hypo_rescue_log`).

**Going-forward policy (BA, per N4):** each future drill entry attaches the
**captured command transcript**, not typed output. Prose attestation alone is no
longer sufficient for this `[SAFETY]` drill.
