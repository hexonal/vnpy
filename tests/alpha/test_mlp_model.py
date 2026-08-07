"""
Regression tests for MlpModel's training loop.

Three upstream defects are pinned here, all of them silent — the model trained,
logged, and predicted while doing something other than what its parameter names
said:

* **n_steps counts gradient steps.** One `np.random.choice` batch per iteration,
  with replacement. Under its old name `n_epochs` the same number meant ~5
  passes over a 120k-row training set and ~150 passes over a 4k-row one.
* **Early stopping was unreachable arithmetic.** The counter only advances at
  evaluation time, and the old defaults allowed 15 evaluations against a
  patience of 50.
* **The best weights were never restored.** `_evaluate_step` rebuilt
  `best_params = None` on entry, so every non-improving evaluation erased the
  checkpoint the caller was holding — and early stopping is by definition a run
  of non-improving evaluations.

A fourth defect — `detail()` scoring feature importance by perturbing
`torch.randn` rows instead of real ones — needs a dataset the synthetic rows
cannot imitate, so it gets its own fake. `FakeDataset` draws every column from
`rng.standard_normal`, which is `torch.randn`'s own distribution and therefore
proves nothing about where the rows came from; `ShapedDataset` adds a constant
column and a rare-event column, and both readings collapse under synthetic
input.

Two of the tests here are weaker than they look, and are kept for what they do
cover rather than what they appear to. Replaying the upstream file with nothing
changed but the two parameter names leaves 4 of the 15 green, because the step
budget was only ever misnamed — the loop always ran one batch per iteration —
so `test_n_steps_*` pin an invariant rather than catch a regression. They do
fail if the loop is rewritten to count passes over the data, which is the
mistake the old name invited.

The doubles here are hand-written fakes: a dataset is just something with
`fetch_learn` / `fetch_infer` returning a polars frame shaped
`[datetime, vt_symbol, *features, label]`, which is all MlpModel reads.
"""

from __future__ import annotations

import copy
from datetime import datetime, timedelta

import numpy as np
import polars as pl
import pytest
import torch

from vnpy.alpha import Segment
from vnpy.alpha.model.models.mlp_model import MlpModel


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeDataset:
    """Minimal stand-in for AlphaDataset — only the two fetch methods matter."""

    def __init__(
        self,
        n_features: int,
        n_train: int = 4000,
        n_valid: int = 1000,
        valid_sign: float = 1.0,
        noise: float = 0.3,
        seed: int = 7
    ) -> None:
        rng = np.random.default_rng(seed)
        self._frames: dict[Segment, pl.DataFrame] = {}

        for segment, rows, sign in (
            (Segment.TRAIN, n_train, 1.0),
            (Segment.VALID, n_valid, valid_sign),
        ):
            features = rng.standard_normal((rows, n_features))

            # Only column 0 carries signal — everything else is noise, which is
            # what permutation importance has to recover.
            label = sign * 2.0 * features[:, 0] + rng.standard_normal(rows) * noise

            data: dict = {
                "datetime": [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(rows)],
                "vt_symbol": [f"S{i % 5}.HK" for i in range(rows)],
            }
            for column in range(n_features):
                data[f"f{column}"] = features[:, column]
            data["label"] = label

            self._frames[segment] = pl.DataFrame(data)

    def fetch_learn(self, segment: Segment) -> pl.DataFrame:
        return self._frames[segment]

    def fetch_infer(self, segment: Segment) -> pl.DataFrame:
        return self._frames[segment]


class ShapedDataset:
    """A dataset whose columns have shapes that `torch.randn` cannot imitate.

    `FakeDataset` draws every feature from `rng.standard_normal`, which is the
    same distribution `torch.randn` produces — so it is structurally incapable
    of telling real feature rows from synthetic ones, and the old
    `_calculate_feature_importance` would have passed every test written on it.
    Two columns here are shaped to break that tie:

    * ``f2`` is **constant**. Permuting a constant column is a no-op, so its
      importance has to be exactly 0.0. Under synthetic rows the same column is
      noise and scores something.
    * ``f3`` is a **rare event** — 1.0 on about 2% of rows. Permuting it moves
      roughly 4% of predictions a long way and leaves the rest untouched, which
      is the shape that separates a mean from a standard deviation.
    """

    def __init__(self, rows_train: int = 4000, rows_valid: int = 1000) -> None:
        self._frames: dict[Segment, pl.DataFrame] = {}

        for segment, rows, seed in (
            (Segment.TRAIN, rows_train, 7),
            (Segment.VALID, rows_valid, 8),
        ):
            rng = np.random.default_rng(seed)
            features = rng.standard_normal((rows, 6))
            features[:, 2] = 5.0
            features[:, 3] = (rng.random(rows) < 0.02).astype(float)

            label = (
                2.0 * features[:, 0]
                + 1.5 * features[:, 1]
                + 16.0 * features[:, 3]
                + rng.standard_normal(rows) * 0.3
            )

            data: dict = {
                "datetime": [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(rows)],
                "vt_symbol": [f"S{i % 5}.HK" for i in range(rows)],
            }
            for column in range(6):
                data[f"f{column}"] = features[:, column]
            data["label"] = label

            self._frames[segment] = pl.DataFrame(data)

    def fetch_learn(self, segment: Segment) -> pl.DataFrame:
        return self._frames[segment]

    def fetch_infer(self, segment: Segment) -> pl.DataFrame:
        return self._frames[segment]


class RecordingCheckpoints:
    """Wraps _evaluate_step and keeps a copy of every improved checkpoint."""

    def __init__(self, model: MlpModel) -> None:
        self.model = model
        self.wrapped = model._evaluate_step
        self.snapshots: dict[int, dict] = {}
        self.steps: list[int] = []
        model._evaluate_step = self  # type: ignore[method-assign]

    def __call__(self, train_valid_data, evaluation_results, step, train_loss, *rest):  # noqa: ANN001
        out = self.wrapped(train_valid_data, evaluation_results, step, train_loss, *rest)
        self.steps.append(step)
        if out[2] is not None:
            self.snapshots[step] = copy.deepcopy(out[2])
        return out


class StubEvaluation:
    """Replaces _evaluate_step and always hands back one fixed checkpoint.

    Lets a test drive `fit` to a chosen `best_params` — including values a real
    optimiser never produces — without training anything into that state.
    """

    def __init__(self, model: MlpModel, checkpoint: dict | None) -> None:
        self.checkpoint: dict | None = checkpoint
        model._evaluate_step = self  # type: ignore[method-assign]

    def __call__(self, train_valid_data, evaluation_results, step, train_loss, early_stop_count, best_valid_score, best_params):  # noqa: ANN001
        return early_stop_count, best_valid_score, self.checkpoint


class RecordingRestore:
    """Records what fit() tried to load back, leaving the real weights alone."""

    def __init__(self, model: MlpModel) -> None:
        self.calls: list[dict] = []
        model.model.load_state_dict = self  # type: ignore[method-assign]

    def __call__(self, state: dict) -> None:
        self.calls.append(state)


class CountingTrainStep:
    """Wraps _train_step and counts how many gradient updates actually ran."""

    def __init__(self, model: MlpModel) -> None:
        self.wrapped = model._train_step
        self.calls = 0
        model._train_step = self  # type: ignore[method-assign]

    def __call__(self, *args):  # noqa: ANN002
        self.calls += 1
        return self.wrapped(*args)


PROBE_WEIGHT = "network.1.weight"


def max_weight_gap(state: dict, other: dict) -> float:
    """Largest absolute element-wise gap on one representative weight matrix."""
    return (state[PROBE_WEIGHT].cpu() - other[PROBE_WEIGHT].cpu()).abs().max().item()


# ---------------------------------------------------------------------------
# n_steps is a step budget, not an epoch budget
# ---------------------------------------------------------------------------

def test_n_steps_runs_exactly_that_many_gradient_updates() -> None:
    model = MlpModel(input_size=6, n_steps=60, eval_steps=20, early_stop_evals=2, seed=42)
    counter = CountingTrainStep(model)

    model.fit(FakeDataset(n_features=6, n_train=4000), {})

    assert counter.calls == 60


def test_n_steps_ignores_training_set_size_so_it_cannot_mean_epochs() -> None:
    # A ten-fold larger training set would run ten times as many updates if the
    # budget were counted in passes. It runs the same 60 either way.
    small = MlpModel(input_size=6, n_steps=60, eval_steps=20, early_stop_evals=2, seed=42)
    small_counter = CountingTrainStep(small)
    small.fit(FakeDataset(n_features=6, n_train=400), {})

    large = MlpModel(input_size=6, n_steps=60, eval_steps=20, early_stop_evals=2, seed=42)
    large_counter = CountingTrainStep(large)
    large.fit(FakeDataset(n_features=6, n_train=4000), {})

    assert small_counter.calls == large_counter.calls == 60


# ---------------------------------------------------------------------------
# Early stopping has to be reachable
# ---------------------------------------------------------------------------

def test_constructor_refuses_an_early_stop_budget_the_loop_can_never_spend() -> None:
    # The old upstream defaults, spelled out: 300 // 20 = 15 evaluations, of
    # which the first always improves, against a patience of 50.
    with pytest.raises(ValueError, match="早停永远不会触发"):
        MlpModel(input_size=6, n_steps=300, eval_steps=20, early_stop_evals=50)


def test_constructor_accepts_the_smallest_reachable_combination() -> None:
    # 1020 // 20 == 51 evaluations, counter ceiling 50 — exactly reachable.
    model = MlpModel(input_size=6, n_steps=1020, eval_steps=20, early_stop_evals=50)

    assert model.n_steps == 1020


def test_default_hyperparameters_leave_early_stopping_reachable() -> None:
    model = MlpModel(input_size=6)

    n_evals = model.n_steps // model.eval_steps
    assert n_evals - 1 >= model.early_stop_evals


def test_early_stopping_fires_after_that_many_non_improving_evaluations() -> None:
    # Validation labels are sign-flipped against training labels, so validation
    # loss worsens monotonically once the network starts learning.
    model = MlpModel(
        input_size=8,
        n_steps=5000,
        eval_steps=1,
        early_stop_evals=5,
        batch_size=512,
        lr=0.05,
        seed=42,
    )
    recorder = RecordingCheckpoints(model)

    model.fit(FakeDataset(n_features=8, valid_sign=-1.0), {})

    assert len(recorder.steps) < 5000
    assert model.best_step is not None
    assert recorder.steps[-1] - model.best_step == 5


# ---------------------------------------------------------------------------
# The best checkpoint survives to the end of fit
# ---------------------------------------------------------------------------

def test_early_stopped_fit_restores_the_weights_from_the_best_evaluation() -> None:
    model = MlpModel(
        input_size=8,
        n_steps=5000,
        eval_steps=1,
        early_stop_evals=5,
        batch_size=512,
        lr=0.05,
        seed=42,
    )
    recorder = RecordingCheckpoints(model)

    model.fit(FakeDataset(n_features=8, valid_sign=-1.0), {})

    best = recorder.snapshots[model.best_step]
    assert max_weight_gap(model.model.state_dict(), best) == pytest.approx(0.0, abs=1e-12)


def test_best_weights_are_restored_even_when_early_stopping_never_fires() -> None:
    # The defect was never conditional on early stopping: the rollback ran only
    # when the very last evaluation happened to be the best one.
    model = MlpModel(
        input_size=8,
        n_steps=40,
        eval_steps=1,
        early_stop_evals=38,
        batch_size=512,
        lr=0.05,
        seed=42,
    )
    recorder = RecordingCheckpoints(model)

    model.fit(FakeDataset(n_features=8, valid_sign=-1.0), {})

    assert recorder.steps[-1] == 40
    assert model.best_step != 40
    best = recorder.snapshots[model.best_step]
    assert max_weight_gap(model.model.state_dict(), best) == pytest.approx(0.0, abs=1e-12)


def test_non_improving_evaluation_hands_back_the_carried_checkpoint_unchanged() -> None:
    model = MlpModel(input_size=4, n_steps=100, eval_steps=20, early_stop_evals=3, seed=42)
    dataset = FakeDataset(n_features=4, n_train=200, n_valid=200)

    train_valid_data: dict[str, dict] = {"x": {}, "y": {}}
    for segment in (Segment.TRAIN, Segment.VALID):
        df = dataset.fetch_learn(segment).sort(["datetime", "vt_symbol"])
        features = df.select(df.columns[2: -1]).to_numpy()
        train_valid_data["x"][segment] = torch.from_numpy(features).float()
        train_valid_data["y"][segment] = torch.from_numpy(np.array(df["label"])).float()

    carried = copy.deepcopy(model.model.state_dict())
    evaluation_results: dict = {Segment.TRAIN: [], Segment.VALID: []}

    # best_valid_score of -inf can never be beaten, so this evaluation cannot improve.
    count, score, params = model._evaluate_step(
        train_valid_data, evaluation_results, 20, 1.0, 0, -np.inf, carried
    )

    assert count == 1
    assert score == -np.inf
    assert params is carried


# ---------------------------------------------------------------------------
# Feature importance reads real data and is reproducible
# ---------------------------------------------------------------------------

def test_detail_returns_none_like_the_other_alpha_models() -> None:
    model = MlpModel(input_size=6, n_steps=60, eval_steps=20, early_stop_evals=2, seed=42)
    model.fit(FakeDataset(n_features=6), {})

    assert model.detail() is None


def test_permutation_importance_gives_the_same_ranking_on_every_call() -> None:
    model = MlpModel(input_size=6, n_steps=200, eval_steps=20, early_stop_evals=5, seed=42)
    dataset = FakeDataset(n_features=6)
    model.fit(dataset, {})

    first = model.permutation_importance(dataset, Segment.VALID)
    second = model.permutation_importance(dataset, Segment.VALID)

    assert list(first.index) == list(second.index)
    assert first["Importance"].tolist() == pytest.approx(second["Importance"].tolist())


def test_permutation_importance_ranks_the_only_informative_feature_first() -> None:
    model = MlpModel(input_size=6, n_steps=600, eval_steps=20, early_stop_evals=10, seed=42)
    dataset = FakeDataset(n_features=6)
    model.fit(dataset, {})

    importance = model.permutation_importance(dataset, Segment.VALID)

    assert importance.index[0] == "f0"


def test_permutation_importance_before_fit_refuses_instead_of_returning_noise() -> None:
    model = MlpModel(input_size=6)

    with pytest.raises(ValueError, match="尚未训练"):
        model.permutation_importance(FakeDataset(n_features=6), Segment.VALID)


def test_permutation_importance_scores_a_constant_feature_at_exactly_zero() -> None:
    # The one assertion that can tell real feature rows from `torch.randn` rows.
    # A column that never varies in the data cannot carry information, and
    # permuting it is bit-for-bit a no-op, so the score is exactly 0.0 rather
    # than approximately so. Feed the same network synthetic rows instead and
    # that column becomes noise: measured, it scores 0.0411 while a genuinely
    # informative one scores 2.1166.
    model = MlpModel(input_size=6, n_steps=600, eval_steps=20, early_stop_evals=10, seed=42)
    dataset = ShapedDataset()
    model.fit(dataset, {})

    importance = model.permutation_importance(dataset, Segment.VALID)

    assert importance.loc["f2", "Importance"] == 0.0
    assert importance["Importance"].max() > 0.0


def test_permutation_importance_does_not_rank_a_rare_event_above_a_dense_feature() -> None:
    # Pins the scoring statistic, which the ranking of a dense feature alone
    # cannot: mean(|delta|) and std(delta) agree on almost every panel, because
    # a permutation leaves the marginal distribution intact and the resulting
    # deltas are centred. A rare event is where they part. f3 fires on 2% of
    # rows, so permuting it moves ~4% of predictions and leaves the rest at
    # zero; measured over three seeds, std/mean is 5.13 for that column against
    # 1.25 for the dense ones, a 4.1x relative inflation. With the weights here
    # that is enough to flip the order outright — f3 places third on
    # mean(|delta|) (0.579 against f1's 1.575) and FIRST on std(delta) (2.97
    # against 1.98), ahead even of f0.
    model = MlpModel(input_size=6, n_steps=600, eval_steps=20, early_stop_evals=10, seed=42)
    dataset = ShapedDataset()
    model.fit(dataset, {})

    importance = model.permutation_importance(dataset, Segment.VALID)

    assert importance.index[0] == "f0"
    assert importance.loc["f1", "Importance"] > importance.loc["f3", "Importance"]


# ---------------------------------------------------------------------------
# The rollback guard itself
# ---------------------------------------------------------------------------

def test_fit_restores_an_empty_checkpoint_rather_than_skipping_it() -> None:
    # `if best_params:` is a truthiness test and an empty state_dict is falsy,
    # so the guard has to read `is not None`. No optimiser hands back an empty
    # state_dict, which is why the checkpoint is stubbed rather than trained
    # into existence — without this the comment in `fit` asserts a hazard that
    # nothing demonstrates, and the two spellings are indistinguishable.
    model = MlpModel(input_size=6, n_steps=60, eval_steps=20, early_stop_evals=2, seed=42)
    StubEvaluation(model, {})
    recorder = RecordingRestore(model)

    model.fit(FakeDataset(n_features=6, n_train=200, n_valid=200), {})

    assert recorder.calls == [{}]


def test_fit_skips_the_restore_when_no_checkpoint_was_ever_taken() -> None:
    # The other side of the same guard: None means "nothing to go back to", and
    # calling load_state_dict(None) would raise rather than no-op.
    model = MlpModel(input_size=6, n_steps=60, eval_steps=20, early_stop_evals=2, seed=42)
    StubEvaluation(model, None)
    recorder = RecordingRestore(model)

    model.fit(FakeDataset(n_features=6, n_train=200, n_valid=200), {})

    assert recorder.calls == []
