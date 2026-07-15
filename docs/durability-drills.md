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
