import numpy as np
import polars as pl
from sklearn.linear_model import Lasso      # type: ignore

from vnpy.alpha import (
    AlphaDataset,
    AlphaModel,
    Segment,
    logger
)
from vnpy.alpha.dataset import LABEL_NAME, feature_names, select_features


class LassoModel(AlphaModel):
    """LASSO regression learning algorithm"""

    def __init__(
        self,
        alpha: float = 0.0005,
        max_iter: int = 1000,
        random_state: int | None = None,
    ) -> None:
        """
        Parameters
        ----------
        alpha : float
            Regularization parameter
        max_iter : int
            Maximum number of iterations
        random_state : int
            Random seed
        """
        self.alpha: float = alpha
        self.max_iter: int = max_iter
        self.random_state: int | None = random_state

        self.model: Lasso = None

        self.feature_names: list[str] = []

    def fit(self, dataset: AlphaDataset) -> None:
        """
        Fit the model with dataset

        Parameters
        ----------
        dataset : AlphaDataset
            The dataset used for training
        """
        # Get training data — TRAIN only, matching LgbModel/MlpModel.
        # Previously this concatenated TRAIN+VALID and fit on the union,
        # which made any VALID-segment metric for Lasso in-sample while
        # the other two models' VALID metrics are genuinely held-out —
        # an apples-to-oranges model comparison inside one framework.
        # VALID stays available for hyperparameter selection by callers.
        df_train: pl.DataFrame = dataset.fetch_learn(Segment.TRAIN)
        df_train = df_train.unique(subset=["datetime", "vt_symbol"])
        df_train = df_train.sort(["datetime", "vt_symbol"])

        # Extract feature names by name, not by position — the old
        # df.columns[2:-1] handed `label` to the model as its own strongest
        # input the moment anything sat after it, and detail() then printed
        # that coefficient as if it were a factor. See dataset/template.py.
        self.feature_names = feature_names(df_train)

        # Convert to numpy arrays
        X: np.ndarray = df_train.select(self.feature_names).to_numpy()
        y: np.ndarray = np.array(df_train[LABEL_NAME])

        # Create and train the model
        self.model = Lasso(
            alpha=self.alpha,
            max_iter=self.max_iter,
            random_state=self.random_state,
            fit_intercept=False,
            copy_X=False
        )
        self.model.fit(X, y)

    def predict(self, dataset: AlphaDataset, segment: Segment) -> np.ndarray:
        """
        Make predictions using the model

        Parameters
        ----------
        dataset : AlphaDataset
            The dataset used for prediction
        segment : Segment
            The segment of data to use for prediction

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

        # Get data for prediction
        df: pl.DataFrame = dataset.fetch_infer(segment)
        df = df.sort(["datetime", "vt_symbol"])

        # fit() already recorded the exact column names; reuse them instead
        # of slicing the inference frame independently, so training and
        # inference cannot drift apart column by column.
        data: np.ndarray = select_features(df, self.feature_names).to_numpy()

        # Return prediction results
        result: np.ndarray = self.model.predict(data)

        return result

    def detail(self) -> None:
        """
        Output detailed information about the model

        Displays feature importance based on the coefficients
        of the LASSO model, showing only non-zero features
        sorted by absolute value.
        """
        # Get feature coefficients
        coef: np.ndarray = self.model.coef_

        # Extract feature coefficients
        data: list[tuple[str, float]] = list(zip(self.feature_names, coef, strict=False))

        # Filter non-zero features
        data = [x for x in data if x[1]]

        # Sort by absolute value
        data.sort(key=lambda x: abs(x[1]), reverse=True)

        # Filter out features with very small coefficients
        data = [x for x in data if round(x[1], 6) != 0]

        # Print feature importance
        logger.info(f"LASSO模型特征总数量: {len(data)}")

        for name, importance in data:
            logger.info(f"{name}: {importance:.6f}")
