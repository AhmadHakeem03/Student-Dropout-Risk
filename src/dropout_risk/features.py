"""Feature engineering (row-wise, stateless) and feature selection (fitted on real training rows)."""

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_selection import mutual_info_classif

from .data import NOMINAL_COLUMNS, TOOL_COLUMNS

# name -> (required base columns, function). A feature is built only if all its inputs exist.
ENGINEERED_FEATURES = {
    "n_ai_tools": (TOOL_COLUMNS, lambda X: X[TOOL_COLUMNS].sum(axis=1)),
    "ai_search_substitution": (
        ["ai_replaces_research", "ai_replaces_search_engines"],
        lambda X: X["ai_replaces_research"] + X["ai_replaces_search_engines"]),
    "ai_dependency_index": (
        ["ai_study_frequency", "over_reliance", "ai_replaces_research"],
        lambda X: X["ai_study_frequency"] + X["over_reliance"] + X["ai_replaces_research"]),
    "integrity_risk_count": (
        ["submitted_full_project", "used_ai_in_exam", "flagged_by_professor"],
        lambda X: X["submitted_full_project"] + X["used_ai_in_exam"] + X["flagged_by_professor"]),
    "negative_impact_count": (
        ["analytical_skills_effect", "motivation_effect", "independent_learning"],
        lambda X: (X["analytical_skills_effect"] == 0).astype(int)
        + (X["motivation_effect"] == 0).astype(int)
        + (X["independent_learning"] == 0).astype(int)),
    "perceived_benefit": (
        ["saves_time", "ai_improved_education"],
        lambda X: X["saves_time"] + X["ai_improved_education"]),
    "ai_literacy": (
        ["detector_knowledge", "learned_prompting", "gave_advice"],
        lambda X: X["detector_knowledge"] + (X["learned_prompting"] == 1).astype(int) + X["gave_advice"]),
    "detection_awareness": (
        ["detector_knowledge", "easy_to_detect"],
        lambda X: X["detector_knowledge"] + X["easy_to_detect"]),
    "is_senior": (["study_year"], lambda X: (X["study_year"] >= 4).astype(int)),
}


def engineer_features(X: pd.DataFrame) -> pd.DataFrame:
    """Add engineered features and one-hot encode nominal columns. Deterministic per row."""
    X = pd.DataFrame(X).copy()
    for name, (inputs, fn) in ENGINEERED_FEATURES.items():
        if all(c in X.columns for c in inputs):
            X[name] = fn(X).astype(int)
    for col, codes in NOMINAL_COLUMNS.items():
        if col in X.columns:
            for code in codes:  # fixed category list -> identical columns in every CV fold
                X[f"{col}_{code}"] = (X[col] == code).astype(int)
            X = X.drop(columns=col)
    return X


class ColumnSelector(BaseEstimator, TransformerMixin):
    """Keep a fixed list of columns (the output of `select_features`)."""

    def __init__(self, columns=None):
        self.columns = columns

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        return X[list(self.columns)]


def select_features(X: pd.DataFrame, y: pd.Series, cfg: dict) -> tuple[list[str], pd.DataFrame]:
    """Pick the top-k features from engineered REAL training data.

    1. drop quasi-constant features
    2. score each feature by mutual information and Random-Forest impurity importance;
       combined score = mean of the two rank percentiles
    3. of highly correlated pairs (|Spearman| >= threshold), drop the lower-scored one
    4. keep the top_k by combined score
    """
    fcfg, seed = cfg["features"], cfg["random_state"]
    report = pd.DataFrame(index=X.columns)
    report["top_value_share"] = [X[c].value_counts(normalize=True).iloc[0] for c in X.columns]
    report["status"] = np.where(report["top_value_share"] >= fcfg["quasi_constant_threshold"],
                                "dropped: quasi-constant", "")

    candidates = report.index[report["status"] == ""].tolist()
    Xc = X[candidates]
    report.loc[candidates, "mutual_info"] = mutual_info_classif(
        Xc, y, discrete_features=True, random_state=seed)
    rf = RandomForestClassifier(n_estimators=500, class_weight="balanced", random_state=seed, n_jobs=-1)
    report.loc[candidates, "rf_importance"] = rf.fit(Xc, y).feature_importances_
    report.loc[candidates, "score"] = (report.loc[candidates, "mutual_info"].rank(pct=True)
                                       + report.loc[candidates, "rf_importance"].rank(pct=True)) / 2

    ordered = report.loc[candidates, "score"].sort_values(ascending=False).index.tolist()
    corr = Xc.corr(method="spearman").abs()
    kept: list[str] = []
    for feat in ordered:
        partner = next((k for k in kept if corr.loc[feat, k] >= fcfg["correlation_threshold"]), None)
        if partner:
            report.loc[feat, "status"] = f"dropped: correlated with {partner}"
        else:
            kept.append(feat)

    selected = kept[: fcfg["top_k"]]
    report.loc[selected, "status"] = "selected"
    report.loc[kept[fcfg["top_k"]:], "status"] = "dropped: below top_k"
    return selected, report.sort_values("score", ascending=False)
