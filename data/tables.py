"""SQLAlchemy ORM tables — the persistent schema (04-data-model.md).

Structural guarantees baked into the schema so corruption is impossible, not
merely discouraged:

- ``meal_event.net_carbs_g`` is a **DB-computed** column
  ``max(carbs_g - fiber_g, 0)`` — flooring lives in the schema, so no write
  path can persist a negative net-carb value.
- ``bolus_offset_min`` is a plain signed integer (negative = pre-bolus).
- ``datetime`` (reported) and ``logged_at`` (system clock) are separate columns;
  **no clinical timestamp carries a now() default** (ADR-8). Only columns the
  data model marks "system clock — correct here" default to ``func.now()``.
- ``patient_profile`` is **append-only**: an in-place UPDATE raises
  ``ProfileImmutableError``; a change is a new version row (REQ-054).
"""

from __future__ import annotations

import datetime as dt
import enum
from typing import Any

from sqlalchemy import (
    JSON,
    Computed,
    Connection,
    ForeignKey,
    event,
    func,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Mapper, mapped_column


class Base(DeclarativeBase):
    pass


class ProfileImmutableError(Exception):
    """Raised on an attempt to UPDATE a patient_profile row in place (REQ-054).

    Clinical constants are versioned: change them by inserting a new version,
    never by overwriting an existing row.
    """


# --- Enumerations ----------------------------------------------------------


class ISFSource(enum.StrEnum):
    default = "default"
    endo = "endo"
    derived = "derived"


class BolusType(enum.StrEnum):
    meal = "meal"
    correction = "correction"
    combined = "combined"


class LoggedBy(enum.StrEnum):
    patient = "patient"
    operator = "operator"


class MealType(enum.StrEnum):
    breakfast = "breakfast"
    lunch = "lunch"
    dinner = "dinner"
    snack = "snack"


class ExIntensity(enum.StrEnum):
    none = "none"
    light = "light"
    intense = "intense"


class DishSource(enum.StrEnum):
    IFCT2017 = "IFCT2017"
    USDA = "USDA"
    label = "label"
    estimated = "estimated"


# --- Tables ----------------------------------------------------------------


class PatientProfile(Base):
    """Versioned clinical constants — never updated in place (REQ-054)."""

    __tablename__ = "patient_profile"

    profile_id: Mapped[int] = mapped_column(primary_key=True)
    effective_from: Mapped[dt.date] = mapped_column()
    icr: Mapped[float | None] = mapped_column(default=None)  # null ⇒ calculator refuses (S-1011)
    isf: Mapped[float] = mapped_column(default=30.0)
    isf_source: Mapped[ISFSource] = mapped_column(SAEnum(ISFSource), default=ISFSource.default)
    target_bg: Mapped[int] = mapped_column(default=135)
    bolus_brand: Mapped[str] = mapped_column(default="Fiasp")
    basal_brand: Mapped[str] = mapped_column(default="Tresiba")
    hypo_unaware: Mapped[bool] = mapped_column(default=True)


class BolusLog(Base):
    """Every injection — the sole source of truth for IOB (REQ-006)."""

    __tablename__ = "bolus_log"

    bolus_id: Mapped[int] = mapped_column(primary_key=True)
    datetime: Mapped[dt.datetime] = mapped_column()  # REPORTED
    logged_at: Mapped[dt.datetime] = mapped_column()  # system clock
    units: Mapped[float] = mapped_column()
    bolus_type: Mapped[BolusType] = mapped_column(SAEnum(BolusType))
    meal_id: Mapped[int | None] = mapped_column(ForeignKey("meal_event.meal_id"), default=None)
    logged_by: Mapped[LoggedBy] = mapped_column(SAEnum(LoggedBy))


class BasalLog(Base):
    """Daily Tresiba (REQ-007)."""

    __tablename__ = "basal_log"

    date: Mapped[dt.date] = mapped_column(primary_key=True)
    units: Mapped[float] = mapped_column()
    time_taken: Mapped[dt.time] = mapped_column()  # REPORTED
    logged_at: Mapped[dt.datetime] = mapped_column()


class MealEvent(Base):
    """The training record (REQ-002)."""

    __tablename__ = "meal_event"

    meal_id: Mapped[int] = mapped_column(primary_key=True)
    datetime: Mapped[dt.datetime] = mapped_column()  # REPORTED — when she ATE
    logged_at: Mapped[dt.datetime] = mapped_column()  # system clock, never for datetime
    logged_by: Mapped[LoggedBy] = mapped_column(SAEnum(LoggedBy))
    meal_type: Mapped[MealType] = mapped_column(SAEnum(MealType))
    pre_bg: Mapped[int] = mapped_column()
    pre_bg_time: Mapped[dt.datetime] = mapped_column()  # REPORTED
    post_bg: Mapped[int | None] = mapped_column(default=None)
    post_bg_time: Mapped[dt.datetime | None] = mapped_column(default=None)  # REPORTED
    elapsed_min: Mapped[int | None] = mapped_column(default=None)  # stored even if invalid
    meal_bolus_units: Mapped[float] = mapped_column()
    correction_bolus_units: Mapped[float] = mapped_column(default=0.0)
    bolus_offset_min: Mapped[int] = mapped_column()  # SIGNED: negative = pre-bolus
    carbs_g: Mapped[float] = mapped_column()
    protein_g: Mapped[float] = mapped_column(default=0.0)
    fat_g: Mapped[float] = mapped_column(default=0.0)
    fiber_g: Mapped[float] = mapped_column(default=0.0)
    net_carbs_g: Mapped[float] = mapped_column(
        Computed("max(carbs_g - fiber_g, 0)", persisted=True)
    )
    macro_confidence: Mapped[int] = mapped_column(default=95)
    ex_intensity: Mapped[ExIntensity] = mapped_column(
        SAEnum(ExIntensity), default=ExIntensity.none
    )
    ex_duration_min: Mapped[int] = mapped_column(default=0)
    ex_offset_min: Mapped[int | None] = mapped_column(default=None)
    pre_ex_intensity: Mapped[ExIntensity] = mapped_column(
        SAEnum(ExIntensity), default=ExIntensity.none
    )
    pre_ex_duration_min: Mapped[int] = mapped_column(default=0)
    hypo_treatment: Mapped[bool] = mapped_column(default=False)
    hypo_treatment_g: Mapped[float | None] = mapped_column(default=None)
    snack_during_window: Mapped[bool] = mapped_column(default=False)
    notes: Mapped[str | None] = mapped_column(default=None)
    is_valid: Mapped[bool] = mapped_column(default=False)  # computed — S-203
    exclusion_reasons: Mapped[str | None] = mapped_column(default=None)  # all, not first
    # ★ The client's per-submission UUID (`05 §`, S-1016). UNIQUE **at the database**: a
    # read-then-insert races, and one submission producing two rows also produces two
    # BOLUS rows — which corrupts IOB, and the calculator subtracts IOB. Nullable, and
    # several NULLs coexist: every meal recorded before S-1016 has no key, and inventing
    # one would fabricate provenance (DL-055).
    idempotency_key: Mapped[str | None] = mapped_column(
        unique=True, index=True, default=None
    )


class CorrectionEvent(Base):
    """Standalone corrections with no food — the clean ISF signal (REQ-013)."""

    __tablename__ = "correction_event"

    event_id: Mapped[int] = mapped_column(primary_key=True)
    datetime: Mapped[dt.datetime] = mapped_column()  # REPORTED
    logged_at: Mapped[dt.datetime] = mapped_column()
    bg_before: Mapped[int] = mapped_column()
    # +4 h reading + its reported time arrive at the follow-up, not at create
    # (two-phase capture, S-306) — nullable until then.
    bg_after: Mapped[int | None] = mapped_column(default=None)
    bg_after_time: Mapped[dt.datetime | None] = mapped_column(default=None)  # REPORTED
    units: Mapped[float] = mapped_column()
    # DEFERRED to S-401: iob_at() derives this from bolus_log; NULL means "not yet
    # known" and is excluded from the clean ISF set (07 §6). Never hand-entered.
    iob_at_start: Mapped[float | None] = mapped_column(default=None)  # valid only if < 0.5
    food_in_window: Mapped[bool] = mapped_column()


class HypoRescueLog(Base):
    """An independent, append-only ledger of hypo rescues (REQ-012, INV-7).

    Deliberately **decoupled** from ``meal_event``: ``meal_id`` is a plain integer
    reference, **not** a cascading foreign key, so deleting a meal row cannot erase
    its rescue record. This independence is what lets INV-7 catch a rescued meal
    row that vanished from the database — the flag-and-row disappear together, this
    ledger entry does not (04 §5 INV-7 / DL-019, audit H4). Never updated in place;
    a rescue is a fact that happened.
    """

    __tablename__ = "hypo_rescue_log"

    rescue_id: Mapped[int] = mapped_column(primary_key=True)
    # Plain reference — NOT a ForeignKey. A meal-row deletion must not cascade here.
    meal_id: Mapped[int] = mapped_column()
    grams: Mapped[float | None] = mapped_column(default=None)
    # System clock is correct here: this is the record's write time, not a
    # clinical (reported) timestamp (ADR-8).
    logged_at: Mapped[dt.datetime] = mapped_column()


class Dish(Base):
    """The adherence mechanism — a repeat meal in a few taps (REQ-009)."""

    __tablename__ = "dish"

    dish_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()
    portion_unit: Mapped[str] = mapped_column()
    carbs_g: Mapped[float] = mapped_column()
    protein_g: Mapped[float] = mapped_column()
    fat_g: Mapped[float] = mapped_column()
    fiber_g: Mapped[float] = mapped_column()
    source: Mapped[DishSource] = mapped_column(SAEnum(DishSource))
    is_favourite: Mapped[bool] = mapped_column(default=False)
    needs_review: Mapped[bool] = mapped_column(default=False)


class PredictionLog(Base):
    """Every prediction, persisted BEFORE it is returned (INV-9)."""

    __tablename__ = "prediction_log"

    prediction_id: Mapped[int] = mapped_column(primary_key=True)
    # System clock is correct here (04 §8).
    created_at: Mapped[dt.datetime] = mapped_column(server_default=func.now())
    meal_id: Mapped[int | None] = mapped_column(ForeignKey("meal_event.meal_id"), default=None)
    model_version: Mapped[str] = mapped_column()  # required for shadow-mode analysis
    gate_state: Mapped[str] = mapped_column()
    input_features: Mapped[dict[str, Any]] = mapped_column(JSON)
    predicted_distribution: Mapped[dict[str, Any]] = mapped_column(JSON)
    baseline_state: Mapped[int] = mapped_column()
    guardrail_fired: Mapped[str | None] = mapped_column(default=None)
    actual_state: Mapped[int | None] = mapped_column(default=None)  # backfilled


class ModelArtifact(Base):
    """A fitted model + its manifest (06 §6)."""

    __tablename__ = "model_artifact"

    version: Mapped[str] = mapped_column(primary_key=True)
    fit_date: Mapped[dt.datetime] = mapped_column()
    data_hash: Mapped[str] = mapped_column()
    n_rows: Mapped[int] = mapped_column()
    feature_list: Mapped[list[str]] = mapped_column(JSON)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON)
    is_promoted: Mapped[bool] = mapped_column(default=False)  # manual only
    kill_switch_tripped: Mapped[bool] = mapped_column(default=False)  # manual re-arm only
    # The fitted model itself, as plain inspectable JSON (S-1014). NULL on every artifact
    # written before that story — real history, and the loader returns None rather than
    # raising. Never a pickle: unpickling executes code, and a blob cannot answer "what does
    # this model do?" (DL-052).
    fitted_model: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)


class AuditLog(Base):
    """Every edit to a clinical record (04 §10)."""

    __tablename__ = "audit_log"

    audit_id: Mapped[int] = mapped_column(primary_key=True)
    table_name: Mapped[str] = mapped_column()
    record_id: Mapped[int] = mapped_column()
    field: Mapped[str] = mapped_column()
    old_value: Mapped[str] = mapped_column()
    new_value: Mapped[str] = mapped_column()
    # System clock is correct here.
    changed_at: Mapped[dt.datetime] = mapped_column(server_default=func.now())
    changed_by: Mapped[LoggedBy] = mapped_column(SAEnum(LoggedBy))


@event.listens_for(PatientProfile, "before_update")
def _forbid_patient_profile_update(
    mapper: Mapper[PatientProfile], connection: Connection, target: PatientProfile
) -> None:
    """REQ-054: patient_profile is append-only. Change it with a new version."""
    raise ProfileImmutableError(
        "patient_profile is versioned and must not be updated in place; "
        "insert a new version row instead (REQ-054)"
    )
