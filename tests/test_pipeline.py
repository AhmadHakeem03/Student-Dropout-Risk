import numpy as np
import pandas as pd
import pytest

from dropout_risk import data as D
from dropout_risk.config import load_config
from dropout_risk.features import engineer_features, select_features
from dropout_risk.main import pick_best
from dropout_risk.synthetic import build_synthetic_dataset


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def encoded(cfg):
    return D.encode_survey(D.load_raw(cfg["data"]["raw_path"], cfg["data"]["sheet"]))


@pytest.fixture(scope="module")
def split(cfg, encoded):
    X, y = encoded
    return D.split(X, y, cfg)


def test_encoding_is_complete_and_integer(encoded):
    X, y = encoded
    assert len(X) == 183 and X.notna().all().all()
    assert all(pd.api.types.is_integer_dtype(t) for t in X.dtypes)
    assert set(y.unique()) == {0, 1}
    assert "drop_risk_score" not in X.columns  # determines the label -> would leak the target


def test_unknown_answer_raises():
    with pytest.raises(ValueError, match="Unmapped"):
        D._map(pd.Series(["نعم", "ربما"]), D.YES_NO, "x")


def test_split_is_stratified_and_disjoint(split, cfg):
    X_train, X_test, y_train, y_test = split
    assert not set(X_train.index) & set(X_test.index)
    assert abs(y_train.mean() - y_test.mean()) < 0.03
    assert len(X_test) == round(183 * cfg["split"]["test_size"])


def test_smoten_creates_only_valid_answers(split, cfg):
    X_train, _, y_train, _ = split
    syn = build_synthetic_dataset(X_train, y_train, cfg)
    target = cfg["smote"]["samples_per_class"]
    assert syn[y_train.name].value_counts().to_dict() == {0: target, 1: target}
    assert syn["is_synthetic"].sum() == 2 * target - len(X_train)
    real = syn[syn["is_synthetic"] == 0].drop(columns=["is_synthetic"])
    pd.testing.assert_frame_equal(real.reset_index(drop=True),
                                  X_train.join(y_train).reset_index(drop=True), check_dtype=False)
    for col in X_train.columns:  # every synthetic value is an answer seen in the real data
        assert set(syn[col]) <= set(X_train[col])


def test_feature_engineering_is_deterministic_rowwise(split):
    X_train = split[0]
    full = engineer_features(X_train)
    parts = pd.concat([engineer_features(X_train.iloc[:20]), engineer_features(X_train.iloc[20:])])
    pd.testing.assert_frame_equal(full, parts)
    assert "major" not in full and {f"major_{c}" for c in range(5)} <= set(full.columns)


def test_select_features_respects_top_k(split, cfg):
    X_train, _, y_train, _ = split
    selected, report = select_features(engineer_features(X_train), y_train, cfg)
    assert len(selected) == cfg["features"]["top_k"] and len(set(selected)) == len(selected)
    assert (report.loc[selected, "status"] == "selected").all()
    assert "ever_used_ai" not in selected  # 97% "yes" -> quasi-constant


def test_pick_best_breaks_ties_by_auc_then_simplicity():
    df = pd.DataFrame({
        "model": ["a", "b", "c"], "cv_f1": [0.9001, 0.9004, 0.85],
        "cv_roc_auc": [0.95, 0.95, 0.99], "complexity": [3, 1, 0],
    })
    assert pick_best(df, "f1") == "b"
    df.loc[0, "cv_roc_auc"] = 0.97
    assert pick_best(df, "f1") == "a"
