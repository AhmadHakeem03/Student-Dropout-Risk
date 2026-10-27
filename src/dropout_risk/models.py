"""The five candidate models, their search spaces, and the SMOTEN -> features -> model pipeline."""

from dataclasses import dataclass, field
from typing import Callable

from catboost import CatBoostClassifier
from imblearn.pipeline import Pipeline
from scipy.stats import loguniform
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import RandomizedSearchCV, RepeatedStratifiedKFold
from sklearn.preprocessing import FunctionTransformer, StandardScaler
from sklearn.tree import DecisionTreeClassifier
from xgboost import XGBClassifier

from .features import ColumnSelector, engineer_features
from .synthetic import make_sampler

SCORING = ["f1", "roc_auc", "average_precision", "recall", "precision", "accuracy", "balanced_accuracy"]


@dataclass
class ModelSpec:
    name: str
    label: str
    build: Callable[[int], object]          # random_state -> unfitted estimator
    params: dict = field(default_factory=dict)  # search space, without the "model__" prefix
    scale: bool = False
    complexity: int = 0                     # tie-breaker: simpler wins


MODELS = [
    ModelSpec(
        "logistic_regression", "Logistic Regression",
        lambda seed: LogisticRegression(max_iter=5000, random_state=seed),
        {"C": loguniform(1e-3, 1e2)},
        scale=True, complexity=0),
    ModelSpec(
        "decision_tree", "Decision Tree",
        lambda seed: DecisionTreeClassifier(random_state=seed),
        {"max_depth": [2, 3, 4, 5, 6, 8, None], "min_samples_leaf": [1, 2, 5, 10, 20],
         "criterion": ["gini", "entropy"], "ccp_alpha": [0.0, 0.001, 0.005, 0.01]},
        complexity=1),
    ModelSpec(
        "random_forest", "Random Forest",
        lambda seed: RandomForestClassifier(random_state=seed, n_jobs=1),
        {"n_estimators": [200, 400], "max_depth": [None, 4, 6, 8, 12],
         "min_samples_leaf": [1, 2, 5], "max_features": ["sqrt", 0.5]},
        complexity=2),
    ModelSpec(
        "xgboost", "XGBoost",
        lambda seed: XGBClassifier(random_state=seed, n_jobs=1, eval_metric="logloss"),
        {"n_estimators": [100, 200, 400], "max_depth": [2, 3, 4, 6],
         "learning_rate": [0.03, 0.1, 0.3], "subsample": [0.7, 1.0],
         "colsample_bytree": [0.7, 1.0], "min_child_weight": [1, 3, 5]},
        complexity=3),
    ModelSpec(
        "catboost", "CatBoost",
        lambda seed: CatBoostClassifier(random_seed=seed, verbose=0, thread_count=1,
                                        allow_writing_files=False),
        {"iterations": [200, 400], "depth": [3, 4, 6], "learning_rate": [0.03, 0.1],
         "l2_leaf_reg": [1, 3, 10]},
        complexity=4),
]


def build_pipeline(spec: ModelSpec, cfg: dict, selected: list[str]) -> Pipeline:
    """SMOTEN runs first (only on training data, also inside each CV fold), then features are
    engineered from the resampled base answers and reduced to the selected set."""
    steps = [
        ("smoten", make_sampler(cfg)),
        ("engineer", FunctionTransformer(engineer_features)),
        ("select", ColumnSelector(selected)),
    ]
    if spec.scale:
        steps.append(("scale", StandardScaler()))
    steps.append(("model", spec.build(cfg["random_state"])))
    return Pipeline(steps)


def tune(spec: ModelSpec, cfg: dict, selected: list[str], X, y) -> RandomizedSearchCV:
    t = cfg["training"]
    cv = RepeatedStratifiedKFold(n_splits=t["cv_splits"], n_repeats=t["cv_repeats"],
                                 random_state=cfg["random_state"])
    search = RandomizedSearchCV(
        build_pipeline(spec, cfg, selected),
        {f"model__{k}": v for k, v in spec.params.items()},
        n_iter=t["n_iter"], scoring=SCORING, refit=t["primary_metric"], cv=cv,
        n_jobs=t["n_jobs"], random_state=cfg["random_state"], error_score="raise",
    )
    return search.fit(X, y)
