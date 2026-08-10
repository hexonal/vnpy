"""The label column is found by name, never by position.

lgb/lasso/mlp used to read their feature matrix off `df.columns[2:-1]`,
which encodes the convention that prepare_data() sorts `label` last. All
eleven shipped processors do keep it last, so no shipped pipeline ever
tripped — but add_processor() takes an arbitrary callable, and a single
processor that leaves one column behind after `label` shifted the slice
to [f1..fN, label]. fit() then handed the label in as an input feature
and as y at the same time, predict() sliced the same way, and the column
count still matched, so LightGBM/sklearn/torch all accepted it silently.

Measured on the real hk_bluechip_10 daily panel before the fix: `label`
took 99.9965% of LightGBM's gain and TEST corr(signal, label) went from
0.004942 to 0.999952.

These tests use tiny synthetic frames rather than the lab parquet — the
defect is entirely about column bookkeeping, and a frame small enough to
read in one screen makes the shift visible.
"""

import polars as pl
import pytest

from vnpy.alpha.dataset import LABEL_NAME, feature_names, select_features


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_frame(columns: list[str]) -> pl.DataFrame:
    """Build a frame whose column ORDER is the thing under test."""
    return pl.DataFrame({name: [float(i)] for i, name in enumerate(columns)})


LABELLED = ["datetime", "vt_symbol", "kmid", "klen", "ma_5", LABEL_NAME]

SHIFTED = ["datetime", "vt_symbol", "kmid", "klen", "ma_5", LABEL_NAME, "liquid_flag"]


# ---------------------------------------------------------------------------
# feature_names
# ---------------------------------------------------------------------------

def test_feature_names_on_a_conventional_frame_matches_the_old_positional_slice() -> None:
    df = make_frame(LABELLED)
    assert feature_names(df) == df.columns[2:-1] == ["kmid", "klen", "ma_5"]


def test_feature_names_excludes_the_label_when_another_column_follows_it() -> None:
    df = make_frame(SHIFTED)

    # This is the whole defect in one line: the positional slice would have
    # returned the label as the last feature.
    assert df.columns[2:-1] == ["kmid", "klen", "ma_5", LABEL_NAME]
    assert feature_names(df) == ["kmid", "klen", "ma_5", "liquid_flag"]


def test_feature_names_treats_a_trailing_column_as_a_feature_not_as_a_replacement() -> None:
    df = make_frame(SHIFTED)
    assert LABEL_NAME not in feature_names(df)
    assert "liquid_flag" in feature_names(df)


def test_feature_names_refuses_a_frame_with_no_label_instead_of_donating_a_feature() -> None:
    df = make_frame(["datetime", "vt_symbol", "kmid", "klen", "ma_5"])

    # The positional slice would have silently answered ["kmid", "klen"].
    with pytest.raises(ValueError, match="set_label"):
        feature_names(df)


def test_feature_names_ignores_index_key_position() -> None:
    df = make_frame(["vt_symbol", "datetime", "kmid", LABEL_NAME])
    assert feature_names(df) == ["kmid"]


# ---------------------------------------------------------------------------
# select_features
# ---------------------------------------------------------------------------

def test_select_features_returns_the_recorded_columns_in_the_recorded_order() -> None:
    df = make_frame(["datetime", "vt_symbol", "klen", "kmid", LABEL_NAME])
    selected = select_features(df, ["kmid", "klen"])
    assert selected.columns == ["kmid", "klen"]


def test_select_features_accepts_an_inference_frame_carrying_no_label() -> None:
    # The live case: the forward-looking label cannot exist for the newest
    # bar, and the old positional slice lost a real feature over it.
    df = make_frame(["datetime", "vt_symbol", "kmid", "klen", "ma_5"])
    assert select_features(df, ["kmid", "klen", "ma_5"]).width == 3


def test_select_features_refuses_when_a_trained_feature_is_absent() -> None:
    df = make_frame(["datetime", "vt_symbol", "kmid", LABEL_NAME])

    with pytest.raises(ValueError, match="ma_5"):
        select_features(df, ["kmid", "ma_5"])


def test_select_features_truncates_a_long_missing_list_but_keeps_the_count() -> None:
    df = make_frame(["datetime", "vt_symbol", LABEL_NAME])
    wanted = [f"f_{i}" for i in range(158)]

    with pytest.raises(ValueError, match="共 158 列"):
        select_features(df, wanted)
