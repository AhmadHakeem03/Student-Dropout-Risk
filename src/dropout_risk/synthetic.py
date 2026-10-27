"""Synthetic oversampling with SMOTEN (SMOTE for nominal features).

Every base feature is a category code, so plain SMOTE's linear interpolation would invent answers
that don't exist. SMOTEN builds each synthetic row from the most common answer among the seed row's
k nearest same-class neighbours (Value Difference Metric), so every synthetic value is a valid answer.
"""

from functools import partial
from pathlib import Path

import numpy as np
import pandas as pd
from imblearn.over_sampling import SMOTEN

from .data import load_dataset, split


def _per_class_target(y, samples_per_class: int) -> dict:
    """Oversample every class up to `samples_per_class` (never below its current count)."""
    classes, counts = np.unique(y, return_counts=True)
    return {c: max(int(samples_per_class), int(n)) for c, n in zip(classes, counts)}


def make_sampler(cfg: dict) -> SMOTEN:
    s = cfg["smote"]
    return SMOTEN(
        sampling_strategy=partial(_per_class_target, samples_per_class=s["samples_per_class"]),
        k_neighbors=s["k_neighbors"],
        random_state=cfg["random_state"],
    )


def build_synthetic_dataset(X_train: pd.DataFrame, y_train: pd.Series, cfg: dict) -> pd.DataFrame:
    """Real training rows + SMOTEN rows, with an `is_synthetic` flag. imblearn appends synthetic
    rows after the originals, which is how the flag is assigned."""
    X_res, y_res = make_sampler(cfg).fit_resample(X_train, y_train)
    out = pd.DataFrame(X_res, columns=X_train.columns).astype(int)
    out[y_train.name] = np.asarray(y_res)
    out["is_synthetic"] = (np.arange(len(out)) >= len(X_train)).astype(int)
    return out


def write_processed_datasets(cfg: dict) -> dict[str, Path]:
    """Encode the survey, split it, and write the real train/test sets plus the SMOTEN-augmented
    training set (all base features) to `data.processed_dir`. Returns the written paths."""
    X, y = load_dataset(cfg)
    X_train, X_test, y_train, y_test = split(X, y, cfg)
    out_dir = cfg["data"]["processed_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "encoded_full": out_dir / "survey_encoded.csv",
        "train_real": out_dir / "train_real.csv",
        "test_real": out_dir / "test_real.csv",
        "train_synthetic": out_dir / "train_smoten.csv",
    }
    X.join(y).to_csv(paths["encoded_full"], index_label="row_id")
    X_train.join(y_train).to_csv(paths["train_real"], index_label="row_id")
    X_test.join(y_test).to_csv(paths["test_real"], index_label="row_id")
    build_synthetic_dataset(X_train, y_train, cfg).to_csv(paths["train_synthetic"], index=False)
    return paths
