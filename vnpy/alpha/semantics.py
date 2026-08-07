"""
Feature semantics versioning and degeneracy screening for alpha artifacts
=========================================================================

This module exists because of a failure mode this fork has already lived
through once: the feature pipeline was corrected, every number downstream
changed, and **nothing anywhere raised**. A dataset pickle, a booster pickle
and a signal parquet computed under the old semantics load cleanly under the
new code, predict cleanly, and produce a report that looks exactly like the
one before. The run manifest did not help either — it fingerprints
``{symbols, row_count, span}``, all three of which are identical across a pure
calculation change.

Three separate mechanisms, because each one covers what the previous one
cannot:

* **The stamp.** ``FEATURE_SEMANTICS_VERSION`` is bumped whenever a released
  feature's *value* changes meaning. ``AlphaLab`` writes it into every artifact
  it saves and refuses every artifact it loads that does not carry the current
  one. Refusing rather than warning is the whole point: the surrounding code is
  full of fail-open paths (a missing dataset file logs an error and returns
  ``None``), and a warning about an artifact that still loads is a warning
  nobody acts on.

* **The history table.** A version number alone tells the next reader that
  something changed, not what. ``SEMANTICS_HISTORY`` says what moved and which
  artifacts it invalidated, so a stamp mismatch is a sentence rather than a
  puzzle.

* **The health readout.** ``describe_feature_health`` turns "is this column
  still carrying information" into numbers a protocol file can freeze. This is
  the part the stamp cannot do: a stamp proves *which code* built an artifact,
  never that the result is any good.

**What the stamp does not prove.** ``stamp`` runs unconditionally inside
``AlphaLab.save_*``, so the value it writes says which code *saved* the
artifact, never which code *computed* it. Handing a v0 object straight to
``save_dataset`` mints a v1 stamp on it and the gate then waves it through —
measured, not feared. The seam has one realistic route: migrating old artifacts
by reading them with a bare ``pickle.load`` (which bypasses the gate) and
writing them back through the lab. Migration must therefore move files, not
rewrite them through ``AlphaLab`` — which is why the recorded procedure renames
the old artifacts aside and recomputes from bars, rather than re-saving them.
Closing the seam properly would mean stamping at computation time inside
``AlphaDataset.prepare_data``, which is the hot path and still would not cover
an artifact assembled by hand.

**Why the health readout reports instead of refusing.** The obvious-looking
alternative — assert at load time that every feature is non-degenerate — was
measured and rejected. A degenerate column can be an entirely legitimate
consequence of the input data: with a lab whose ``turnover`` was synthesised as
``close * volume``, a correctly normalized ``vwap_0`` is *exactly* 1.0 on every
row, and there is nothing wrong with either the code or the data. A gate that
fires on legitimate inputs gets switched off within the week. The numbers are
therefore produced for the record, and the judgement is left to whoever writes
the protocol.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import polars as pl


class AlphaSemanticsError(Exception):
    """Raised when an artifact's feature semantics do not match this code.

    Deliberately not a subclass of anything the alpha package already catches.
    The callers of ``AlphaLab.load_dataset`` / ``load_model`` / ``load_signal``
    treat a ``None`` return as "not there yet" and carry on; an artifact built
    under different semantics is a different thing entirely — silently
    continuing with it is the exact outcome this module exists to prevent.
    """


# The current feature semantics. Bump this — and the local version segment in
# `vnpy/__init__.py` alongside it — whenever a shipped feature's values change
# meaning. Rolling either one back without the other is the one manoeuvre that
# turns this module from a guard into a hazard: the check is an equality test,
# so old code carrying a new constant would happily stamp and accept artifacts
# built under the old semantics.
FEATURE_SEMANTICS_VERSION: int = 2

# The attribute written onto pickled artifacts, and the parquet key-value
# metadata key written into signal files.
STAMP_ATTRIBUTE: str = "feature_semantics_version"

# What an artifact carrying no stamp at all is taken to be. Not a free choice:
# the stamp was introduced *as* v1, so anything without one predates it, and
# `SEMANTICS_HISTORY[0]` is the entry describing that state.
#
# Named rather than written as a literal `0` because the two unstamped branches
# below used to render `SEMANTICS_HISTORY[FEATURE_SEMANTICS_VERSION]` instead —
# only the newest release. While the table held one entry that was accidentally
# the same sentence, so the bug could not be seen; the moment v2 landed, a v0
# artifact started being told only what v2 changed and never heard about v1's
# vwap rebase or Float64 cast at all. Measured: `describe_gap(0)` renders 2359
# characters naming both releases, the old expression 1495 naming only v2.
UNSTAMPED_VERSION: int = 0


@dataclass(frozen=True)
class SemanticsRelease:
    """One entry in the semantics changelog."""

    version: int
    summary: str
    invalidates: str

    def describe(self) -> str:
        """Render for an error message or a run manifest."""
        return f"v{self.version}: {self.summary} — invalidates: {self.invalidates}"


SEMANTICS_HISTORY: dict[int, SemanticsRelease] = {
    0: SemanticsRelease(
        version=0,
        summary=(
            "Upstream vnpy 4.4.0 semantics. `load_bar_df` left vwap in raw price units while "
            "rebasing open/high/low/close on close_0, so Alpha158's vwap_0 was a per-symbol "
            "constant (a stock identifier) and every Alpha101 vwap expression was off by that "
            "constant. The five lossy rolling operators truncated integer inputs, so Alpha158's "
            "fifteen cnt* features were 0/1 indicators instead of fractions and Alpha101's "
            "alpha92 collapsed to a single value."
        ),
        invalidates="everything built before this module existed; such artifacts carry no stamp",
    ),
    1: SemanticsRelease(
        version=1,
        summary=(
            "vwap is rebased by the same close_0 as the price columns, and ts_rank / ts_mean / "
            "ts_std / ts_quantile / ts_decay_linear cast their input to Float64 before "
            "rolling_map. Measured against v0 on a synthetic five-symbol panel whose volume is "
            "Float64: 15 of Alpha158's 158 columns move on the operator change (all cnt*, 143 "
            "bit-identical) and one more on the vwap change (vwap_0). The 15 is conditional on "
            "that dtype and not a property of the change — re-measured with an Int64 volume "
            "column, 25 move, the extra ten being vma_5..60 and vstd_5..60, which were being "
            "truncated by the same operators. `load_bar_df` always emits Float64 (the "
            "suspended-day NaN mask promotes it), so the lab path really does see 15; an "
            "AlphaDataset built from a frame assembled some other way need not."
        ),
        invalidates="every dataset pickle, model pickle and signal parquet built under v0",
    ),
    2: SemanticsRelease(
        version=2,
        summary=(
            "DataProxy's four ordering comparisons mask NaN to null before comparing, so a "
            "suspended day is no longer handed a verdict. Under v1 polars answered `NaN > 11.0` "
            "with True and `12.0 > NaN` with False, which booked the first halted day as a rise "
            "and deleted the real rise on the day trading resumed; the Int32 cast and the rolling "
            "mean then buried it, leaving no NaN, no dtype change and no warning behind. "
            "Alpha158's fifteen cnt* features are the entire blast radius. Measured with one "
            "three-day halt on an 800-row synthetic panel (0.375% of rows): exactly those 15 "
            "columns move — cntd_5 by 0.800 on a column whose range is [-1, 1], cntp_5 by 0.600 "
            "on [0, 1] — 411 cells in total, with no reading going missing at that halt length. "
            "Longer halts do make readings go missing, by design: a halt of h sessions blanks "
            "h + 1 flags (the halted days plus the resumption day, whose ts_delay(close, 1) is "
            "itself a halted day), so a window of w has nothing left to average once h >= w - 1. "
            "Measured on one symbol: w=5 loses its first reading at h=4 and h - 3 of them "
            "thereafter, while w=10/20/60 are still lossless at h=8. Alpha158's narrowest window "
            "is 5, so a four-session suspension already blanks cntp_5/cntn_5/cntd_5 and "
            "process_drop_na then drops those rows. `vnpy_alphakit`'s fingerprint "
            "fixture, which carries a suspended day every 37 days and runs the full "
            "save_bar_data -> load_bar_df -> prepare_data path, names the same fifteen columns "
            "and no others. Measured on panels with no "
            "suspended row in them, including hk_bluechip_10 (7350 rows, 0 mask hits): all 158 "
            "columns bit-identical, so a v1 artifact built from suspension-free bars carries the "
            "same numbers a v2 one would. The stamp cannot say that — it compares one integer at "
            "load time and never sees the panel — which is why such artifacts are refused too."
        ),
        invalidates=(
            "every dataset pickle, model pickle and signal parquet built under v1 from bars that "
            "contain a suspended day; v1 artifacts from suspension-free panels are numerically "
            "equal to their v2 recomputation and are refused anyway"
        ),
    ),
}

# A feature whose per-date cross section is a single value on more than this
# fraction of dates carries no ranking information on those dates, whatever its
# overall variance says. Chosen as a screening default, not a law — the audit
# that motivated this module found cnt* flat on 4137 of 4172 dates (0.99) while
# the same columns showed a healthy-looking global standard deviation.
FLAT_GROUP_LIMIT: float = 0.5


# ---------------------------------------------------------------------------
# Stamping pickled artifacts
# ---------------------------------------------------------------------------

def stamp(obj: object) -> None:
    """Mark an artifact with the semantics it was built under.

    An attribute rather than a wrapper envelope, on purpose: the pickle on disk
    stays a bare ``AlphaDataset`` / ``AlphaModel``, so third-party code that
    calls ``pickle.load`` directly still gets the object it expects instead of a
    dict it has never seen. Neither class defines ``__slots__``, so the
    attribute sticks.
    """
    setattr(obj, STAMP_ATTRIBUTE, FEATURE_SEMANTICS_VERSION)


def read_stamp(obj: object) -> int | None:
    """Read an artifact's semantics version, or ``None`` if it carries none."""
    value: object = getattr(obj, STAMP_ATTRIBUTE, None)

    if isinstance(value, bool) or not isinstance(value, int):
        return None

    return value


def assert_compatible(obj: object, source: str | Path) -> None:
    """Refuse an artifact that was not built under the current semantics."""
    found: int | None = read_stamp(obj)

    if found is None:
        raise AlphaSemanticsError(
            f"产物 {source} 没有特征语义版本戳，判定为 v0 旧口径，拒绝加载——"
            f"当前代码要求 {STAMP_ATTRIBUTE}={FEATURE_SEMANTICS_VERSION}。"
            f"{describe_gap(UNSTAMPED_VERSION)}。"
            f"请用当前代码重算该产物；改动清单见 vnpy/FORK.md"
        )

    if found != FEATURE_SEMANTICS_VERSION:
        raise AlphaSemanticsError(
            f"产物 {source} 的特征语义版本不匹配：期望 {FEATURE_SEMANTICS_VERSION}，收到 {found}。"
            f"{describe_gap(found)}。"
            f"请用当前代码重算该产物；改动清单见 vnpy/FORK.md"
        )


def describe_gap(found: int) -> str:
    """Spell out every semantics release between an artifact's stamp and now."""
    releases: list[SemanticsRelease] = [
        release
        for version, release in sorted(SEMANTICS_HISTORY.items())
        if found < version <= FEATURE_SEMANTICS_VERSION
    ]

    if not releases:
        return f"本代码没有记录 v{found} 与 v{FEATURE_SEMANTICS_VERSION} 之间的差异"

    return "；".join(release.describe() for release in releases)


# ---------------------------------------------------------------------------
# Stamping parquet artifacts
# ---------------------------------------------------------------------------

def parquet_metadata() -> dict[str, str]:
    """Key-value metadata to write alongside a signal parquet.

    Signals are the artifact that most needs this and can least do without it:
    a signal file holds only datetime / vt_symbol / signal, so unlike a dataset
    or a booster there is no trace of the features inside it. Nothing about the
    file itself can tell an old signal from a new one.
    """
    return {STAMP_ATTRIBUTE: str(FEATURE_SEMANTICS_VERSION)}


def assert_parquet_compatible(file_path: Path) -> None:
    """Refuse a parquet artifact that was not written under the current semantics."""
    metadata: dict[str, str] = pl.read_parquet_metadata(file_path)
    raw: str | None = metadata.get(STAMP_ATTRIBUTE)

    if raw is None:
        raise AlphaSemanticsError(
            f"产物 {file_path} 没有特征语义版本戳，判定为 v0 旧口径，拒绝加载——"
            f"当前代码要求 {STAMP_ATTRIBUTE}={FEATURE_SEMANTICS_VERSION}。"
            f"{describe_gap(UNSTAMPED_VERSION)}。"
            f"请用当前代码重算该产物；改动清单见 vnpy/FORK.md"
        )

    try:
        found: int = int(raw)
    except ValueError:
        raise AlphaSemanticsError(
            f"产物 {file_path} 的特征语义版本戳无法解析为整数，收到 {raw!r}"
        ) from None

    if found != FEATURE_SEMANTICS_VERSION:
        raise AlphaSemanticsError(
            f"产物 {file_path} 的特征语义版本不匹配：期望 {FEATURE_SEMANTICS_VERSION}，收到 {found}。"
            f"{describe_gap(found)}。"
            f"请用当前代码重算该产物；改动清单见 vnpy/FORK.md"
        )


# ---------------------------------------------------------------------------
# Feature health
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FeatureHealth:
    """How much information one feature column still carries.

    ``std`` and ``n_unique`` are computed over the finite values only. Alpha
    frames use NaN for suspended days and for the warm-up rows of every rolling
    window, and a single NaN poisons a whole-column standard deviation into NaN
    — which would report every healthy column as broken and hide the broken
    ones among them.
    """

    name: str
    finite_count: int
    n_unique: int
    std: float
    flat_group_fraction: float

    @property
    def degenerate(self) -> bool:
        """Whether this column is unusable as a cross-sectional signal."""
        # `math.isfinite` rather than a comparison: a NaN std makes every
        # comparison False, so `if self.std <= 0.0` would report a column with
        # no computable variance as healthy — the failure inverted.
        if not self.finite_count or not math.isfinite(self.std):
            return True

        if self.n_unique <= 1:
            return True

        return self.flat_group_fraction >= FLAT_GROUP_LIMIT

    def describe(self) -> str:
        """Render one line for a log or a run manifest."""
        verdict: str = "DEGENERATE" if self.degenerate else "ok"
        return (
            f"{self.name}: finite={self.finite_count} unique={self.n_unique} "
            f"std={self.std:.6f} flat={self.flat_group_fraction:.4f} [{verdict}]"
        )


def describe_feature_health(df: pl.DataFrame, by: str = "datetime") -> list[FeatureHealth]:
    """Measure every numeric column of a feature frame, in column order.

    ``by`` names the column that groups a cross section — one date, normally.
    The per-group reading is what separates "this column has variance" from
    "this column can rank anything": a feature that moves over time but is
    identical across every symbol on any given day has plenty of global
    variance and exactly zero ranking power.

    Non-numeric columns and the grouping column are skipped rather than
    reported, so the returned list can be zipped against a model's feature list.
    """
    if by not in df.columns:
        raise ValueError(f"分组列不在数据中，收到 {by!r}，可用列 {df.columns}")

    healths: list[FeatureHealth] = []

    for name, dtype in df.schema.items():
        if name == by or not dtype.is_numeric():
            continue

        healths.append(measure_feature(df, name, by))

    return healths


def measure_feature(df: pl.DataFrame, name: str, by: str) -> FeatureHealth:
    """Measure a single numeric column of a feature frame."""
    finite: pl.DataFrame = df.select(by, name).filter(finite_predicate(df, name))

    values: pl.Series = finite[name]
    std: float = float("nan")

    if values.len() > 1:
        # Series.std is typed as returning a timedelta for temporal columns;
        # the caller already filtered to numeric dtypes, so this is a float.
        computed: float | None = cast("float | None", values.std())
        if computed is not None:
            std = float(computed)
    elif values.len() == 1:
        std = 0.0

    per_group: pl.DataFrame = finite.group_by(by).agg(pl.col(name).n_unique().alias("distinct"))
    flat_fraction: float = 1.0

    if per_group.height:
        flat_fraction = float((per_group["distinct"] <= 1).sum()) / per_group.height

    return FeatureHealth(
        name=name,
        finite_count=values.len(),
        n_unique=values.n_unique(),
        std=std,
        flat_group_fraction=flat_fraction,
    )


def finite_predicate(df: pl.DataFrame, name: str) -> pl.Expr:
    """Build the "this value is a real number" filter for one column.

    ``is_not_nan`` is only defined for floating dtypes — polars raises
    ``InvalidOperationError`` on an integer column — so the NaN half of the
    predicate is added only where NaN can actually occur.
    """
    predicate: pl.Expr = pl.col(name).is_not_null()

    if df.schema[name].is_float():
        predicate = predicate & pl.col(name).is_not_nan() & pl.col(name).is_finite()

    return predicate
