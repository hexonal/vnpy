"""
Tests for the feature semantics stamp and the feature health readout.

The stamp is the only thing in this codebase that makes a *calculation* change
visible after the fact. Nothing else does: an old dataset pickle unpickles
cleanly under new code, an old booster's ``predict`` passes its own shape check
and returns plausible numbers, and a signal parquet carries no trace of the
features behind it at all. The audit that produced this module measured the
damage on the workspace's one shipped model — feeding it correctly normalized
features moved its predictions by up to 0.4147 while the signal's own standard
deviation was 0.0778, a 5.3x displacement, with no exception raised anywhere.

So the tests below are mostly about **refusal**: the interesting assertions are
the ones where loading fails. Two of them stand in for real artifacts on disk by
pickling an object without a stamp, which is exactly what every pre-v1 pickle
in the workspace is.

The health readout is tested for the opposite property — that it *reports*
rather than refuses, including on a column that is legitimately constant.
"""

from __future__ import annotations

import pickle
from datetime import datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from vnpy.alpha.lab import AlphaLab
from vnpy.alpha.semantics import (
    FEATURE_SEMANTICS_VERSION,
    SEMANTICS_HISTORY,
    STAMP_ATTRIBUTE,
    UNSTAMPED_VERSION,
    AlphaSemanticsError,
    assert_compatible,
    assert_parquet_compatible,
    describe_feature_health,
    read_stamp,
    stamp,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeArtifact:
    """Stands in for AlphaDataset / AlphaModel — the gate only reads one attribute.

    Module level rather than nested so that ``pickle`` can find it again by
    qualified name, the same way a real dataset pickle is found.
    """

    def __init__(self, payload: str = "features") -> None:
        self.payload: str = payload


def make_feature_frame() -> pl.DataFrame:
    """A tiny panel with one healthy column and two broken ones."""
    dates: list[datetime] = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(6)]
    symbols: list[str] = ["A.SEHK", "B.SEHK", "C.SEHK"]

    rows: dict = {"datetime": [], "vt_symbol": [], "healthy": [], "flat_daily": [], "constant": []}

    for day, date in enumerate(dates):
        for index, symbol in enumerate(symbols):
            rows["datetime"].append(date)
            rows["vt_symbol"].append(symbol)

            # Varies both across symbols and over time.
            rows["healthy"].append(0.1 * index + 0.01 * day)

            # Moves over time, identical across the whole cross section on any
            # given day — plenty of global variance, zero ranking power. This
            # is the exact shape the truncated cnt* features had.
            rows["flat_daily"].append(float(day))

            rows["constant"].append(1.0)

    return pl.DataFrame(rows)


# ---------------------------------------------------------------------------
# The stamp itself
# ---------------------------------------------------------------------------

def test_read_stamp_returns_none_for_an_artifact_that_was_never_stamped() -> None:
    assert read_stamp(FakeArtifact()) is None


def test_stamp_then_read_stamp_round_trips_the_current_version() -> None:
    artifact = FakeArtifact()

    stamp(artifact)

    assert read_stamp(artifact) == FEATURE_SEMANTICS_VERSION


def test_assert_compatible_refuses_an_artifact_without_a_stamp() -> None:
    with pytest.raises(AlphaSemanticsError, match="没有特征语义版本戳"):
        assert_compatible(FakeArtifact(), "dataset/hk_bluechip_10.pkl")


def test_assert_compatible_refuses_a_stamp_from_a_different_version() -> None:
    artifact = FakeArtifact()
    setattr(artifact, STAMP_ATTRIBUTE, FEATURE_SEMANTICS_VERSION + 1)

    with pytest.raises(AlphaSemanticsError, match="特征语义版本不匹配"):
        assert_compatible(artifact, "dataset/from_the_future.pkl")


def test_assert_compatible_names_the_offending_file_in_the_message() -> None:
    # The gate fires at import time of somebody else's pipeline; a message that
    # does not say which file is useless in a lab holding a dozen of them.
    with pytest.raises(AlphaSemanticsError, match="hk_bluechip_10"):
        assert_compatible(FakeArtifact(), "dataset/hk_bluechip_10.pkl")


def test_assert_compatible_accepts_a_freshly_stamped_artifact() -> None:
    artifact = FakeArtifact()
    stamp(artifact)

    assert_compatible(artifact, "dataset/fresh.pkl")


def test_refusing_an_unstamped_artifact_names_every_release_since_v0(tmp_path) -> None:  # noqa: ANN001
    # An unstamped artifact is v0 by definition — the stamp shipped *as* v1 — so
    # its owner needs the whole changelog, not the newest entry.
    #
    # Both unstamped branches used to render
    # `SEMANTICS_HISTORY[FEATURE_SEMANTICS_VERSION].describe()`. While the table
    # held a single release that was accidentally the same sentence, so the bug
    # could not be seen; the moment v2 landed, a v0 artifact started being told
    # only what v2 changed and never hearing about v1's vwap rebase or Float64
    # cast at all. Measured: 2359 characters naming both releases against 1495
    # naming one.
    #
    # Written as a loop over the table rather than against a literal "v1:", so
    # that v3 is covered the day it lands instead of the day somebody remembers.
    expected: list[str] = [
        f"v{version}:" for version in range(UNSTAMPED_VERSION + 1, FEATURE_SEMANTICS_VERSION + 1)
    ]

    with pytest.raises(AlphaSemanticsError) as pickle_refusal:
        assert_compatible(FakeArtifact(), "dataset/unstamped.pkl")

    for marker in expected:
        assert marker in str(pickle_refusal.value), marker

    # The parquet branch is a separate copy of the same message, and signals are
    # the artifact with the least other evidence of what built them.
    bare: Path = tmp_path / "unstamped.parquet"
    pl.DataFrame({"signal": [1.0]}).write_parquet(bare)

    with pytest.raises(AlphaSemanticsError) as parquet_refusal:
        assert_parquet_compatible(bare)

    for marker in expected:
        assert marker in str(parquet_refusal.value), marker


def test_every_version_up_to_the_current_one_has_a_history_entry() -> None:
    # A bare version number tells the next reader that something changed but not
    # what. The refusal message quotes this table, so an entry missing here
    # turns a sentence back into a puzzle — and would KeyError inside the raise.
    for version in range(FEATURE_SEMANTICS_VERSION + 1):
        assert version in SEMANTICS_HISTORY
        assert SEMANTICS_HISTORY[version].version == version
        assert SEMANTICS_HISTORY[version].invalidates


# ---------------------------------------------------------------------------
# The gate as AlphaLab actually applies it
# ---------------------------------------------------------------------------

def test_load_dataset_refuses_a_pickle_written_before_the_semantics_stamp(tmp_path) -> None:  # noqa: ANN001
    # Exactly the shape of every artifact currently sitting in
    # vnpy_alphakit/lab/: a bare pickle with no stamp attribute.
    lab: AlphaLab = AlphaLab(str(tmp_path))

    legacy: Path = Path(lab.dataset_path).joinpath("legacy.pkl")
    with open(legacy, mode="wb") as f:
        pickle.dump(FakeArtifact(), f)

    with pytest.raises(AlphaSemanticsError, match="没有特征语义版本戳"):
        lab.load_dataset("legacy")


def test_load_model_refuses_a_pickle_written_before_the_semantics_stamp(tmp_path) -> None:  # noqa: ANN001
    lab: AlphaLab = AlphaLab(str(tmp_path))

    legacy: Path = Path(lab.model_path).joinpath("legacy.pkl")
    with open(legacy, mode="wb") as f:
        pickle.dump(FakeArtifact(), f)

    with pytest.raises(AlphaSemanticsError, match="没有特征语义版本戳"):
        lab.load_model("legacy")


def test_load_signal_refuses_a_parquet_written_before_the_semantics_stamp(tmp_path) -> None:  # noqa: ANN001
    # Signals are the reason the parquet half of the gate exists: the frame has
    # three columns and none of them remembers which features built it.
    lab: AlphaLab = AlphaLab(str(tmp_path))

    frame: pl.DataFrame = pl.DataFrame({
        "datetime": [datetime(2024, 1, 1)],
        "vt_symbol": ["A.SEHK"],
        "signal": [0.5],
    })
    frame.write_parquet(Path(lab.signal_path).joinpath("legacy.parquet"))

    with pytest.raises(AlphaSemanticsError, match="没有特征语义版本戳"):
        lab.load_signal("legacy")


def test_save_then_load_dataset_round_trips_under_the_current_stamp(tmp_path) -> None:  # noqa: ANN001
    lab: AlphaLab = AlphaLab(str(tmp_path))

    lab.save_dataset("fresh", FakeArtifact("payload"))       # type: ignore[arg-type]
    loaded = lab.load_dataset("fresh")

    assert loaded is not None
    assert loaded.payload == "payload"                       # type: ignore[attr-defined]
    assert read_stamp(loaded) == FEATURE_SEMANTICS_VERSION


def test_save_then_load_model_round_trips_under_the_current_stamp(tmp_path) -> None:  # noqa: ANN001
    # The save side needs its own case per artifact kind. A missing `stamp` in
    # `save_model` does not fail like a missing one in `load_model` — the write
    # succeeds and only the NEXT run refuses, which puts the failure a training
    # run away from its cause.
    lab: AlphaLab = AlphaLab(str(tmp_path))

    lab.save_model("fresh", FakeArtifact("booster"))          # type: ignore[arg-type]
    loaded = lab.load_model("fresh")

    assert loaded is not None
    assert loaded.payload == "booster"                        # type: ignore[attr-defined]
    assert read_stamp(loaded) == FEATURE_SEMANTICS_VERSION


def test_save_then_load_signal_round_trips_under_the_current_stamp(tmp_path) -> None:  # noqa: ANN001
    lab: AlphaLab = AlphaLab(str(tmp_path))

    frame: pl.DataFrame = pl.DataFrame({
        "datetime": [datetime(2024, 1, 1), datetime(2024, 1, 2)],
        "vt_symbol": ["A.SEHK", "A.SEHK"],
        "signal": [0.5, -0.25],
    })

    lab.save_signal("fresh", frame)
    loaded = lab.load_signal("fresh")

    assert loaded is not None
    assert loaded["signal"].to_list() == pytest.approx([0.5, -0.25])


def test_saving_an_unstamped_artifact_mints_a_current_stamp_on_it(tmp_path) -> None:  # noqa: ANN001
    # Pins a LIMITATION, not a guarantee. `stamp` runs unconditionally on the
    # way out, so the recorded version says which code saved the artifact, not
    # which code computed it. Anyone migrating old artifacts by reading them
    # with a bare `pickle.load` and writing them back through the lab would
    # forge a v1 stamp onto v0 numbers, and the gate would then pass them.
    # If this ever turns red because stamping moved to computation time, the
    # module docstring's "What the stamp does not prove" paragraph is stale.
    lab: AlphaLab = AlphaLab(str(tmp_path))

    legacy = FakeArtifact("computed under v0")
    assert read_stamp(legacy) is None

    lab.save_dataset("migrated", legacy)                      # type: ignore[arg-type]

    assert read_stamp(lab.load_dataset("migrated")) == FEATURE_SEMANTICS_VERSION


def test_load_dataset_still_returns_none_when_the_file_is_simply_absent(tmp_path) -> None:  # noqa: ANN001
    # The gate must not swallow the pre-existing "not built yet" path — callers
    # branch on None, and turning that into an exception would be a second,
    # unrelated behaviour change riding along with this one.
    lab: AlphaLab = AlphaLab(str(tmp_path))

    assert lab.load_dataset("never_built") is None
    assert lab.load_model("never_built") is None
    assert lab.load_signal("never_built") is None


# ---------------------------------------------------------------------------
# Feature health
# ---------------------------------------------------------------------------

def test_describe_feature_health_skips_the_index_columns() -> None:
    healths = describe_feature_health(make_feature_frame())

    assert [health.name for health in healths] == ["healthy", "flat_daily", "constant"]


def test_describe_feature_health_flags_a_column_that_is_flat_across_the_cross_section() -> None:
    # The column has a perfectly healthy global standard deviation — it is only
    # the per-date reading that exposes it. Measured on the real panel that
    # motivated this: cntn_20 was flat on 735 of 735 dates before the operator
    # fix and on 2 of 735 after.
    healths = {health.name: health for health in describe_feature_health(make_feature_frame())}

    assert healths["flat_daily"].std > 0.0
    assert healths["flat_daily"].flat_group_fraction == pytest.approx(1.0)
    assert healths["flat_daily"].degenerate


def test_describe_feature_health_leaves_a_genuine_feature_alone() -> None:
    healths = {health.name: health for health in describe_feature_health(make_feature_frame())}

    assert healths["healthy"].flat_group_fraction == pytest.approx(0.0)
    assert not healths["healthy"].degenerate


def test_describe_feature_health_flags_a_constant_column() -> None:
    healths = {health.name: health for health in describe_feature_health(make_feature_frame())}

    assert healths["constant"].n_unique == 1
    assert healths["constant"].degenerate


def test_describe_feature_health_ignores_nan_rather_than_reporting_nan_variance() -> None:
    # Alpha frames are full of NaN — suspended days and every rolling window's
    # warm-up rows. A whole-column std over them is NaN, and a NaN std makes
    # every threshold comparison False, i.e. reports the column as healthy.
    frame: pl.DataFrame = make_feature_frame().with_columns(
        pl.when(pl.col("vt_symbol") == "A.SEHK")
        .then(float("nan"))
        .otherwise(pl.col("healthy"))
        .alias("healthy")
    )

    healths = {health.name: health for health in describe_feature_health(frame)}

    assert healths["healthy"].finite_count == 12
    assert healths["healthy"].std > 0.0
    assert not healths["healthy"].degenerate


def test_describe_feature_health_flags_a_column_that_is_entirely_nan() -> None:
    frame: pl.DataFrame = make_feature_frame().with_columns(
        pl.lit(float("nan")).alias("healthy")
    )

    healths = {health.name: health for health in describe_feature_health(frame)}

    assert healths["healthy"].finite_count == 0
    assert healths["healthy"].degenerate


def test_describe_feature_health_refuses_a_grouping_column_that_is_not_there() -> None:
    with pytest.raises(ValueError, match="收到 'trade_date'"):
        describe_feature_health(make_feature_frame(), by="trade_date")


def test_feature_health_describe_says_which_verdict_it_reached() -> None:
    healths = {health.name: health for health in describe_feature_health(make_feature_frame())}

    assert "DEGENERATE" in healths["constant"].describe()
    assert "[ok]" in healths["healthy"].describe()
