from typing import cast

import numpy as np
import polars as pl
import lightgbm as lgb
import matplotlib.pyplot as plt

from vnpy.alpha.dataset import AlphaDataset, LABEL_NAME, Segment, feature_names, select_features
from vnpy.alpha.model import AlphaModel


class LgbModel(AlphaModel):
    """LightGBM ensemble learning algorithm"""

    def __init__(
        self,
        learning_rate: float = 0.1,
        num_leaves: int = 31,
        num_boost_round: int = 1000,
        early_stopping_rounds: int = 50,
        log_evaluation_period: int = 1,
        seed: int | None = None
    ):
        """
        Parameters
        ----------
        learning_rate : float
            Learning rate
        num_leaves : int
            Number of leaf nodes
        num_boost_round : int
            Maximum number of training rounds
        early_stopping_rounds : int
            Number of rounds for early stopping
        log_evaluation_period : int
            Interval rounds for printing training logs
        seed : int | None
            Random seed
        """
        self.params: dict = {
            "objective": "mse",
            "learning_rate": learning_rate,
            "num_leaves": num_leaves,
            "seed": seed
        }

        self.num_boost_round: int = num_boost_round
        self.early_stopping_rounds: int = early_stopping_rounds
        self.log_evaluation_period: int = log_evaluation_period

        self.model: lgb.Booster | None = None

    def _prepare_data(self, dataset: AlphaDataset) -> list[lgb.Dataset]:
        """
        Prepare data for training and validation

        Parameters
        ----------
        dataset : AlphaDataset
            The dataset containing features and labels

        Returns
        -------
        list[lgb.Dataset]
            List of LightGBM datasets for training and validation
        """
        ds: list[lgb.Dataset] = []

        # Process training and validation separately
        for segment in [Segment.TRAIN, Segment.VALID]:
            # Get data for learning
            df: pl.DataFrame = dataset.fetch_learn(segment)
            df = df.sort(["datetime", "vt_symbol"])

            # Features come from feature_names(), not df.columns[2:-1] —
            # the positional slice silently promoted `label` to a feature
            # whenever any column sat after it. See dataset/template.py.
            names: list[str] = feature_names(df)

            # Convert to numpy arrays
            data = df.select(names).to_pandas()
            label = np.array(df[LABEL_NAME])

            # Add training data
            ds.append(lgb.Dataset(data, label=label))

        return ds

    def fit(self, dataset: AlphaDataset) -> None:
        """
        Fit the model using the dataset

        Parameters
        ----------
        dataset : AlphaDataset
            The dataset containing features and labels

        Returns
        -------
        None
        """
        # Prepare task data
        ds: list[lgb.Dataset] = self._prepare_data(dataset)

        # Execute model training
        self.model = lgb.train(
            self.params,
            ds[0],
            num_boost_round=self.num_boost_round,
            valid_sets=ds,
            valid_names=["train", "valid"],
            callbacks=[
                lgb.early_stopping(self.early_stopping_rounds),      # Early stopping callback
                lgb.log_evaluation(self.log_evaluation_period)       # Logging callback
            ]
        )

    def predict(self, dataset: AlphaDataset, segment: Segment) -> np.ndarray:
        """
        Make predictions using the trained model

        Parameters
        ----------
        dataset : AlphaDataset
            The dataset containing features
        segment : Segment
            The segment to make predictions on

        Returns
        -------
        np.ndarray
            Prediction results

        Raises
        ------
        ValueError
            If the model has not been fitted yet
        """
        # Check if model exists
        if self.model is None:
            raise ValueError("model is not fitted yet!")

        # Get data for inference
        df: pl.DataFrame = dataset.fetch_infer(segment)
        df = df.sort(["datetime", "vt_symbol"])

        # Pin inference to the names the Booster itself recorded at fit
        # time. _prepare_data feeds lgb.Dataset a pandas frame, so those
        # names live inside every Booster ever trained here — including
        # the ones already pickled in lab/*/model, which is why this needs
        # no new persisted field.
        data: np.ndarray = select_features(df, self.model.feature_name()).to_numpy()

        # Return prediction results
        result: np.ndarray = cast(np.ndarray, self.model.predict(data))
        return result

    def detail(self) -> None:
        """
        Display model details with feature importance plots

        Generates two plots showing feature importance based on
        'split' and 'gain' metrics.

        Returns
        -------
        None
        """
        if not self.model:
            return

        for importance_type in ["split", "gain"]:
            ax: plt.Axes = lgb.plot_importance(
                self.model,
                max_num_features=50,
                importance_type=importance_type,
                figsize=(10, 20)
            )
            ax.set_title(f"Feature Importance ({importance_type})")
