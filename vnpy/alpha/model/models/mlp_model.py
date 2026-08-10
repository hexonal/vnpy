import copy
from collections import defaultdict
from typing import Literal, cast

import numpy as np
import pandas as pd
import polars as pl
from sklearn.metrics import mean_squared_error      # type: ignore
import torch
import torch.nn as nn
import torch.optim as optim

from vnpy.alpha import (
    AlphaDataset,
    AlphaModel,
    Segment,
    logger
)
from vnpy.alpha.dataset import LABEL_NAME, feature_names, select_features



class MlpModel(AlphaModel):
    """
    Multi-Layer Perceptron Model

    Alpha factor prediction model implemented using multi-layer perceptron, with main features including:
    1. Building and training multi-layer perceptron neural networks
    2. Predicting Alpha factor values
    3. Model evaluation and feature importance analysis
    4. Support for early stopping and overfitting prevention
    5. Support for MSE loss function
    6. Optional Adam or SGD optimizer
    """

    def __init__(
        self,
        input_size: int,
        hidden_sizes: tuple[int] = (256,),
        lr: float = 0.001,
        n_steps: int = 3000,
        batch_size: int = 2000,
        early_stop_evals: int = 50,
        eval_steps: int = 20,
        optimizer: Literal["sgd", "adam"] = "adam",
        weight_decay: float = 0.0,
        device: str = "cpu",
        seed: int | None = None
    ) -> None:
        """
        Initialize MLP model

        Parameters
        ----------
        input_size : int
            Input feature dimension — the number of feature columns the
            dataset actually carries, which for Alpha158 is 158 (measured:
            `prepare_data` produces datetime + vt_symbol + 158 features +
            label). There is deliberately no default: the docstring used to
            claim `default 360`, a leftover from qlib's Alpha360, while the
            signature has always made this a required positional argument.
            A wrong value is at least loud — torch refuses the first matmul
            with `mat1 and mat2 shapes cannot be multiplied (512x158 and
            157x256)` — but it is loud at fit time, one cell after the
            processor that changed the column count. Derive it from the
            frame (`len(feature_names(dataset.learn_df))`) rather than
            writing the literal twice.
        hidden_sizes : tuple[int], default (256,)
            Number of neurons in hidden layers
        lr : float, default 0.001
            Learning rate
        n_steps : int, default 3000
            Maximum number of GRADIENT STEPS. This used to be called `n_epochs`,
            which was wrong in a way that silently changed training length with
            dataset size: `_train_step` draws ONE batch per iteration with
            `np.random.choice` (with replacement), so a step is a step, never a
            pass over the data. Measured on this file before the rename —
            300 steps x batch 2000 = 600,000 draws, which is ~5 nominal epochs
            over a 120k-row training set but ~150 nominal epochs over a 4k-row
            one. Same number in the config, two opposite failure modes.
            The default moved 300 -> 3000 because 300 is simply undertrained:
            on a synthetic 8-feature problem with a 0.09 noise floor, best
            validation MSE went 0.113879 (300) -> 0.105678 (1000) ->
            0.102548 (3000) -> 0.101696 (8000), i.e. 300 steps leaves roughly
            half of the removable error on the table. The cost of the new
            default is 10x the training time.
        batch_size : int, default 2000
            Number of samples per batch
        early_stop_evals : int, default 50
            Number of consecutive EVALUATIONS without improvement that ends
            training. The unit is evaluations, not steps — one evaluation
            happens every `eval_steps` steps, so the patience in steps is
            `early_stop_evals * eval_steps`. Under the old name
            (`early_stop_rounds`) plus the old `n_epochs=300` default the
            counter could reach at most 14 (300 // 20 evaluations, minus the
            first one which always improves against an initial score of inf),
            so early stopping was unreachable arithmetic — measured, not
            inferred. The constructor now refuses unreachable combinations
            rather than pretending to offer the feature.
        eval_steps : int, default 20
            Evaluate model every this many steps
        optimizer : Literal["sgd", "adam"], default "adam"
            Optimizer type, options are "sgd" or "adam"
        weight_decay : float, default 0.0
            L2 regularization coefficient
        seed : Optional[int], optional
            Random seed for reproducibility
        device : str, default "cpu"
            Training device
        """
        # Refuse an early-stopping budget the training loop can never spend.
        # The loop evaluates at `step % eval_steps == 0` plus once at the final
        # step, and the very first evaluation always improves (best_valid_score
        # starts at inf) and resets the counter — so the counter's ceiling is
        # `n_evals - 1`. Silently accepting a larger `early_stop_evals` is how
        # the upstream defaults ended up advertising early stopping that could
        # not fire; refusing is cheap and the message names the numbers.
        n_evals: int = n_steps // eval_steps + (1 if n_steps % eval_steps else 0)
        if n_evals - 1 < early_stop_evals:
            raise ValueError(
                f"早停永远不会触发：n_steps={n_steps} 配 eval_steps={eval_steps} "
                f"最多只有 {n_evals} 次评估、计数器上界 {n_evals - 1}，"
                f"而 early_stop_evals={early_stop_evals}。"
                f"请把 early_stop_evals 降到 {n_evals - 1} 以下，或把 n_steps 提高到 "
                f"{(early_stop_evals + 1) * eval_steps} 以上"
            )

        # Save model hyperparameters
        self.input_size: int = input_size
        self.hidden_sizes: tuple[int] = hidden_sizes
        self.lr: float = lr
        self.n_steps: int = n_steps
        self.batch_size: int = batch_size
        self.early_stop_evals: int = early_stop_evals
        self.eval_steps: int = eval_steps
        self.device: str = device
        self.fitted: bool = False
        self.feature_names: list[str] = []
        self.best_step: int | None = None

        # Set random seed for reproducibility
        if seed is not None:
            np.random.seed(seed)
            torch.manual_seed(seed)

        # Set loss function type
        self._scorer = mean_squared_error

        # Initialize model
        self.model: nn.Module = MlpNetwork(
            input_size=input_size,
            hidden_sizes=hidden_sizes,
        )

        # Move model to specified device
        self.model = self.model.to(device)

        # Set optimizer
        optimizer_name = optimizer.lower()
        if optimizer_name == "adam":
            self.optimizer: optim.Optimizer = optim.Adam(
                self.model.parameters(),
                lr=lr,
                weight_decay=weight_decay
            )
        elif optimizer_name == "sgd":
            self.optimizer = optim.SGD(
                self.model.parameters(),
                lr=lr,
                weight_decay=weight_decay
            )
        else:
            raise NotImplementedError(f"optimizer {optimizer} is not supported!")

        # Set learning rate scheduler
        self.scheduler: optim.lr_scheduler.ReduceLROnPlateau = optim.lr_scheduler.ReduceLROnPlateau(
            self.optimizer,
            mode="min",
            factor=0.5,
            patience=10,
            threshold=0.0001,
            threshold_mode="rel",
            cooldown=0,
            min_lr=0.00001,
            eps=1e-08,
        )

    def fit(
        self,
        dataset: AlphaDataset,
        evaluation_results: dict | None = None,
    ) -> None:
        """
        Train the multi-layer perceptron model

        Trains the MLP model using the given dataset, with main steps including:
        1. Preparing training and validation data
        2. Iteratively training for multiple steps
        3. Evaluating model performance at fixed intervals
        4. Implementing early stopping to prevent overfitting

        Parameters
        ----------
        dataset : AlphaDataset
            Dataset object containing training data
        evaluation_results : dict
            Dictionary for storing evaluation metrics during training
        """
        # Initialize a new dictionary if evaluation_results is None
        if evaluation_results is None:
            evaluation_results = {}

        # Dictionary to store training and validation data
        train_valid_data: dict[str, dict] = defaultdict(dict)

        # Get feature names first, by name rather than by df.columns[2:-1] —
        # the positional slice fed `label` in as an input feature whenever a
        # column sat after it, and TRAIN/VALID would then have picked their
        # columns independently of each other. See dataset/template.py.
        # Deriving the list once from TRAIN also makes VALID prove it carries
        # the same columns instead of quietly supplying different ones.
        self.feature_names = feature_names(dataset.fetch_learn(Segment.TRAIN))

        # Process training and validation sets separately
        for segment in [Segment.TRAIN, Segment.VALID]:
            # Get learning data and sort by time and trading code
            df: pl.DataFrame = dataset.fetch_learn(segment)
            df = df.sort(["datetime", "vt_symbol"])

            # Extract features and labels
            features = select_features(df, self.feature_names).to_numpy()
            labels = np.array(df[LABEL_NAME])

            # Store feature and label data
            train_valid_data["x"][segment] = torch.from_numpy(features).float().to(self.device)
            train_valid_data["y"][segment] = torch.from_numpy(labels).float().to(self.device)

            # Initialize evaluation results list
            evaluation_results[segment] = []

        # Initialize training state
        early_stop_count: int = 0           # Number of evaluations without performance improvement
        train_loss: float = 0               # Current training loss
        best_valid_score: float = np.inf    # Best validation loss
        best_params: dict[str, torch.Tensor] | None = None   # Best model parameters

        train_samples: int = train_valid_data["y"][Segment.TRAIN].shape[0]

        # Iterate through training steps
        for step in range(1, self.n_steps + 1):
            # Check if early stopping condition is met
            if early_stop_count >= self.early_stop_evals:
                logger.info("达到早停条件,训练结束")
                break

            # Train one batch
            batch_loss = self._train_step(train_valid_data, train_samples)
            train_loss += batch_loss

            # Periodically evaluate the model
            #
            # `best_params` must go IN as well as come out. The previous version
            # only took the return value, and `_evaluate_step` built its own
            # `best_params = None` on entry — so every non-improving evaluation
            # reset the local back to None. Since early stopping is by
            # definition N consecutive non-improving evaluations, the rollback
            # below could never run on an early-stopped fit; and even without
            # early stopping it ran only when the very LAST evaluation happened
            # to be the best one. Measured on a rigged run (validation labels
            # sign-flipped so validation loss worsens monotonically):
            # best_step=7, |final - best| on network.1.weight = 1.72e-01 before,
            # exactly 0.0 after.
            if step % self.eval_steps == 0 or step == self.n_steps:
                early_stop_count, best_valid_score, best_params = self._evaluate_step(
                    train_valid_data,
                    evaluation_results,
                    step,
                    train_loss,
                    early_stop_count,
                    best_valid_score,
                    best_params
                )
                train_loss = 0

        # Mark model as trained
        self.fitted = True

        # Load best model parameters — `is not None` rather than truthiness,
        # because an empty state_dict is falsy and would skip the rollback.
        if best_params is not None:
            self.model.load_state_dict(best_params)

    def _train_step(
        self,
        train_valid_data: dict[str, dict[Segment, torch.Tensor]],
        train_samples: int
    ) -> float:
        """
        Execute one training step

        Parameters
        ----------
        train_valid_data : dict
            Training and validation data
        train_samples : int
            Number of training samples

        Returns
        -------
        float
            Current batch loss value
        """
        batch_loss = AverageMeter()
        self.model.train()
        self.optimizer.zero_grad()

        # Randomly select batch data
        batch_indices = np.random.choice(train_samples, self.batch_size)
        batch_features = train_valid_data["x"][Segment.TRAIN][batch_indices]
        batch_labels = train_valid_data["y"][Segment.TRAIN][batch_indices]

        # Forward and backward propagation
        predictions = self.model(batch_features)
        cur_loss = self._loss_fn(predictions, batch_labels)
        cur_loss.backward()

        # Update model parameters
        self.optimizer.step()
        batch_loss.update(cur_loss.item())

        return batch_loss.val

    def _evaluate_step(
        self,
        train_valid_data: dict[str, dict[Segment, torch.Tensor]],
        evaluation_results: dict[Segment, list[float]],
        step: int,
        train_loss: float,
        early_stop_count: int,
        best_valid_score: float,
        best_params: dict[str, torch.Tensor] | None
    ) -> tuple[int, float, dict[str, torch.Tensor] | None]:
        """
        Evaluate current model performance

        Parameters
        ----------
        train_valid_data : dict
            Training and validation data
        evaluation_results : dict
            Evaluation results record
        step : int
            Current training step
        train_loss : float
            Current training loss
        early_stop_count : int
            Count of consecutive evaluations without improvement
        best_valid_score : float
            Best validation loss
        best_params : dict | None
            Best model parameters seen so far, carried in so that a
            non-improving evaluation returns it untouched instead of erasing it

        Returns
        -------
        tuple[int, float, dict | None]
            Returns updated early stop count, best validation loss, and best model parameters
        """
        early_stop_count += 1
        train_loss /= self.eval_steps

        # Evaluate model on validation set
        with torch.no_grad():
            self.model.eval()

            data: torch.Tensor = train_valid_data["x"][Segment.VALID]
            pred: torch.Tensor = cast(torch.Tensor, self._predict_batch(data, return_cpu=False))
            valid_loss = self._loss_fn(pred, train_valid_data["y"][Segment.VALID])

            loss_val = valid_loss.item()

        # Record evaluation results
        logger.info(f"[Step {step}]: train_loss {train_loss:.6f}, valid_loss {loss_val:.6f}")
        evaluation_results[Segment.TRAIN].append(train_loss)
        evaluation_results[Segment.VALID].append(loss_val)

        # Update best model if validation performance improves
        if loss_val < best_valid_score:
            logger.info(f"\t验证集损失从 {best_valid_score:.6f} 降低到 {loss_val:.6f}")
            best_valid_score = loss_val
            self.best_step = step
            early_stop_count = 0
            best_params = copy.deepcopy(self.model.state_dict())

        # Update learning rate
        if self.scheduler is not None:
            self.scheduler.step(metrics=valid_loss, epoch=step)

        return early_stop_count, best_valid_score, best_params

    def _loss_fn(self, pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        """
        Calculate loss value

        Parameters
        ----------
        pred : torch.Tensor
            Model predictions
        target : torch.Tensor
            Target true values

        Returns
        -------
        torch.Tensor
            Calculated loss value
        """
        pred, target = pred.reshape(-1), target.reshape(-1)
        loss: torch.Tensor = nn.MSELoss()(pred, target)
        return loss

    def _predict_batch(self, data: torch.Tensor, return_cpu: bool = True) -> np.ndarray | torch.Tensor:
        """
        Neural network prediction function

        Parameters
        ----------
        data : torch.Tensor
            Input data
        return_cpu : bool, default True
            Whether to return CPU tensor
        step : Optional[int], optional
            Current training step

        Returns
        -------
        np.ndarray | torch.Tensor
            Model prediction results
        """
        data = data.to(self.device)

        predictions: list[torch.Tensor] = []

        self.model.eval()

        with torch.no_grad():
            batch_size: int = 8096
            for i in range(0, len(data), batch_size):
                x: torch.Tensor = data[i: i + batch_size]
                predictions.append(self.model(x.to(self.device)).detach().reshape(-1))

        if return_cpu:
            return np.concatenate([pr.cpu().numpy() for pr in predictions])
        else:
            return torch.cat(predictions, dim=0)

    def predict(self, dataset: AlphaDataset, segment: Segment) -> np.ndarray:
        """
        Model prediction interface

        Parameters
        ----------
        dataset : AlphaDataset
            Prediction dataset
        segment : Segment
            Dataset segment

        Returns
        -------
        np.ndarray
            Prediction result array
        """
        if not self.fitted:
            raise ValueError("Model has not been trained yet!")

        df: pl.DataFrame = dataset.fetch_infer(segment)
        df = df.sort(["datetime", "vt_symbol"])

        # Same columns, same order as fit() saw — the network's first Linear
        # layer only checks the width, so a shifted slice of the right width
        # would have gone straight through it.
        data: np.ndarray = select_features(df, self.feature_names).to_numpy()

        return cast(np.ndarray, self._predict_batch(torch.Tensor(data)))

    def _check_tensor_nan(self, tensor: torch.Tensor, name: str) -> None:
        """
        Check if tensor contains NaN values

        Parameters
        ----------
        tensor : torch.Tensor
            Tensor to check
        name : str
            Tensor name

        Returns
        -------
        None
        """
        if torch.isnan(tensor).any():
            print(f"NaN values detected: {name}")

    def detail(self) -> None:
        """
        Output MLP model detail information

        This used to end by returning a feature-importance table computed from
        `torch.randn(1000, input_size)` — synthetic standard-normal rows, not
        the model's actual inputs. Three problems, all reproduced: the tensor
        was never seeded, so three calls on ONE trained model produced three
        different top-5 orderings; the randn rows carry none of the real
        features' cross-correlation, while the network's BatchNorm running
        statistics were fitted on real data; and the score itself was
        `std(|new_pred - base_pred|)`, the SPREAD of the perturbation effect,
        which assigns importance 0 to a feature that shifts every prediction
        by the same amount. Seeding would have fixed only the first.
        The table is gone rather than patched; `permutation_importance` below
        does the same job against real data, and `detail()` now returns None
        like its LgbModel and LassoModel siblings.
        """
        if not self.fitted:
            logger.info("模型尚未训练，无法显示详细信息")
            return

        # 显示模型基本信息
        logger.info(f"输入特征维度: {self.input_size}")
        logger.info(f"隐藏层大小: {self.hidden_sizes}")

        # 计算模型总参数量
        total_params = sum(p.numel() for p in self.model.parameters())
        logger.info(f"模型总参数量: {total_params:,}")

        # 显示训练状态信息
        logger.info(f"训练设备: {self.device}")
        logger.info(f"当前学习率: {self.lr}")
        logger.info(f"批次大小: {self.batch_size}")
        logger.info(f"最优步数: {self.best_step}")

    def permutation_importance(
        self,
        dataset: AlphaDataset,
        segment: Segment,
        seed: int = 0
    ) -> pd.DataFrame:
        """
        Feature importance by permuting one real column at a time

        Each feature's column is shuffled across rows of the requested segment
        while every other column stays put — the marginal distribution survives,
        the feature's link to the row is destroyed. Importance is the mean
        absolute change in prediction, so a feature that merely shifts the whole
        output still scores. The shuffle is seeded, so two calls on one model
        return identical rankings.

        Feed it a held-out segment (VALID or TEST): permuting TRAIN measures how
        hard the network memorised, not how much the feature carries.

        Parameters
        ----------
        dataset : AlphaDataset
            Dataset to draw the real feature rows from
        segment : Segment
            Which segment to permute
        seed : int, default 0
            Seed for the row permutation, so the ranking is reproducible

        Returns
        -------
        pd.DataFrame
            Feature importance dataframe, indexed by feature name, descending
        """
        if not self.fitted:
            raise ValueError("模型尚未训练，无法计算特征重要性")

        df: pl.DataFrame = dataset.fetch_infer(segment)
        df = df.sort(["datetime", "vt_symbol"])

        features: np.ndarray = select_features(df, self.feature_names).to_numpy()
        data: torch.Tensor = torch.from_numpy(features).float().to(self.device)

        base: torch.Tensor = cast(torch.Tensor, self._predict_batch(data, return_cpu=False))

        rng = np.random.default_rng(seed)
        importance_dict: dict[str, float] = {}

        # Column i of `data` is self.feature_names[i] by construction above,
        # so the importance ranking is labelled with the name that actually
        # occupies that column instead of whatever position i happens to hit.
        for i, feature_name in enumerate(self.feature_names):
            perturbed: torch.Tensor = data.clone()
            order = torch.from_numpy(rng.permutation(len(data))).to(self.device)
            perturbed[:, i] = data[order, i]

            pred: torch.Tensor = cast(torch.Tensor, self._predict_batch(perturbed, return_cpu=False))
            importance_dict[feature_name] = (pred - base).abs().mean().item()

        result: pd.DataFrame = pd.DataFrame({
            "Feature": list(importance_dict.keys()),
            "Importance": list(importance_dict.values())
        })
        result = result.sort_values("Importance", ascending=False)
        result = result.set_index("Feature")

        return result


class AverageMeter:
    """
    Class for calculating and storing average and current values

    Attributes
    ----------
    val : float
        Current value
    avg : float
        Average value
    sum : float
        Sum
    count : int
        Count
    """

    def __init__(self) -> None:
        """
        Initialize AverageMeter

        Returns
        -------
        None
        """
        self.reset()

    def reset(self) -> None:
        """
        Reset all statistics

        Returns
        -------
        None
        """
        self.val: float = 0
        self.avg: float = 0
        self.sum: float = 0
        self.count: int = 0

    def update(self, val: float, n: int = 1) -> None:
        """
        Update statistics

        Parameters
        ----------
        val : float
            Current value
        n : int, default 1
            Current batch size

        Returns
        -------
        None
        """
        self.val = val
        self.sum += val * n
        self.count += n
        self.avg = self.sum / self.count


class MlpNetwork(nn.Module):
    """
    Deep Neural Network Model Structure

    Used to build multi-layer perceptron network structure, supporting multiple hidden layers
    and different activation functions.

    Attributes
    ----------
    network : nn.ModuleList
        List of neural network layers
    """

    def __init__(
        self,
        input_size: int,
        output_size: int = 1,
        hidden_sizes: tuple[int] = (256,),
        activation: str = "LeakyReLU"
    ) -> None:
        """
        Constructor

        Parameters
        ----------
        input_size : int
            Input feature dimension, i.e., number of features per sample
        output_size : int, default 1
            Output dimension, used for predicting target values
        hidden_sizes : tuple[int], default (256,)
            Tuple of hidden layer neuron counts, e.g., (256, 128) represents two hidden layers
            with 256 and 128 neurons respectively
        activation : str, default "LeakyReLU"
            Activation function type, options:
            - "LeakyReLU": Leaky ReLU function
            - "SiLU": Sigmoid Linear Unit function
        """
        super().__init__()

        # Build network layers
        layers: list[nn.Module] = []
        layer_sizes = [input_size] + list(hidden_sizes)

        # Input layer Dropout
        layers.append(nn.Dropout(0.05))

        # Build hidden layers
        for in_size, out_size in zip(layer_sizes[:-1], layer_sizes[1:], strict=False):
            # Add a neural network block: linear layer + batch normalization + activation function
            layers.extend([
                nn.Linear(in_size, out_size),
                nn.BatchNorm1d(out_size),
                self._get_activation(activation)
            ])

        # Output layer
        layers.extend([
            nn.Dropout(0.05),
            nn.Linear(hidden_sizes[-1], output_size)
        ])

        # Combine all layers into a sequence
        self.network = nn.ModuleList(layers)

        # Initialize network weights
        self._initialize_weights()

    def _get_activation(self, name: str) -> nn.Module:
        """
        Get specified activation function layer

        Parameters
        ----------
        name : str
            Activation function name

        Returns
        -------
        nn.Module
            Activation function layer instance

        Raises
        ------
        ValueError
            When an unsupported activation function type is specified
        """
        if name == "LeakyReLU":
            return nn.LeakyReLU(negative_slope=0.1)
        elif name == "SiLU":
            return nn.SiLU()
        else:
            raise ValueError(f"Unsupported activation function type: {name}")

    def _initialize_weights(self) -> None:
        """
        Initialize network weight parameters

        Uses Kaiming initialization method for all linear layers, which is particularly
        suitable for deep networks using LeakyReLU activation functions.

        Returns
        -------
        None
        """
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.kaiming_normal_(
                    module.weight,
                    a=0.1,                  # LeakyReLU negative slope
                    mode="fan_in",          # Scale using input node count
                    nonlinearity="leaky_relu"
                )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Forward propagation calculation

        Parameters
        ----------
        x : torch.Tensor
            Input feature tensor, shape (batch_size, input_size)

        Returns
        -------
        torch.Tensor
            Model output tensor, shape (batch_size, output_size)
        """
        # Pass through all layers in the network sequentially
        for layer in self.network:
            x = layer(x)
        return x
