"""Analytics behind the dashboards. Pure pandas, no web framework, so it can be reused and tested.

Data sources (selectable on every endpoint with `source=`):
- augmented: the SMOTEN-augmented training set (real training respondents + synthetic rows)
- synthetic: only the SMOTEN-generated rows
- original:  all 183 surveyed respondents
"""

import re
from functools import cached_property
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix, roc_auc_score, roc_curve

from ..data import TARGET
from ..features import ENGINEERED_FEATURES
from ..synthetic import write_processed_datasets
from .catalog import (
    ALL_FEATURES, BASE_FEATURES, CLASS_LABELS, GROUPS, INDEX_FEATURES, SEGMENT_FILTERS, TOOL_FEATURES,
)

SOURCES = {
    "augmented": "SMOTE-augmented training data (real + synthetic)",
    "synthetic": "Synthetic rows only (SMOTEN)",
    "original": "Original survey (183 respondents)",
}
BANDS = ["low", "medium", "high"]


class NotReadyError(RuntimeError):
    """Raised when model outputs are missing (the training pipeline hasn't been run)."""


def _add_indices(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for name, (inputs, fn) in ENGINEERED_FEATURES.items():
        df[name] = fn(df).astype(int)
    return df


def _share(n: int, d: int) -> float | None:
    return round(n / d, 4) if d else None


class DashboardService:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.dcfg = cfg["dashboard"]
        self.processed = Path(cfg["data"]["processed_dir"])
        self.outputs = Path(cfg["output_dir"])

    # --- data ------------------------------------------------------------------------------------
    @cached_property
    def frames(self) -> dict[str, pd.DataFrame]:
        if not (self.processed / "train_smoten.csv").exists():
            write_processed_datasets(self.cfg)
        aug = pd.read_csv(self.processed / "train_smoten.csv")
        orig = pd.read_csv(self.processed / "survey_encoded.csv", index_col="row_id")
        orig["is_synthetic"] = 0
        orig["respondent_id"] = orig.index + 1  # matches the survey's Id column
        aug, orig = _add_indices(aug), _add_indices(orig)
        return {"augmented": aug, "synthetic": aug[aug["is_synthetic"] == 1], "original": orig}

    @cached_property
    def train_ids(self) -> set[int]:
        return set(pd.read_csv(self.processed / "train_real.csv", index_col="row_id").index + 1)

    def frame(self, source: str, filters: dict[str, list[int]] | None = None) -> pd.DataFrame:
        if source not in SOURCES:
            raise ValueError(f"Unknown source '{source}'. Use one of {list(SOURCES)}.")
        df = self.frames[source]
        for feat, codes in (filters or {}).items():
            df = df[df[feat].isin(codes)]
        return df

    @staticmethod
    def parse_filters(raw: list[str]) -> dict[str, list[int]]:
        """['major:0', 'major:1', 'study_year:4'] -> {'major': [0, 1], 'study_year': [4]}"""
        out: dict[str, list[int]] = {}
        for item in raw:
            m = re.fullmatch(r"([a-z_]+):(-?\d+)", item.strip())
            if not m or m.group(1) not in ALL_FEATURES:
                raise ValueError(f"Bad filter '{item}'. Expected '<feature>:<code>' with a known feature.")
            out.setdefault(m.group(1), []).append(int(m.group(2)))
        return out

    # --- metadata --------------------------------------------------------------------------------
    def meta(self) -> dict:
        def feat(f):
            return {"name": f.name, "title": f.title, "group": f.group, "actionable": f.actionable,
                    "description": f.description,
                    "answers": [{"code": c, "label": l} for c, l in f.answers.items()]}
        return {
            "sources": [{"id": k, "label": v, "rows": int(len(self.frames[k]))} for k, v in SOURCES.items()],
            "default_source": self.dcfg["default_source"],
            "groups": GROUPS,
            "features": [feat(f) for f in BASE_FEATURES.values()],
            "indices": [feat(f) for f in INDEX_FEATURES.values()],
            "segment_filters": SEGMENT_FILTERS,
            "classes": [{"code": c, "label": l} for c, l in CLASS_LABELS.items()],
            "risk_bands": self.dcfg["risk_bands"],
            "model_ready": (self.outputs / "best_model.joblib").exists(),
        }

    # --- descriptive analytics -------------------------------------------------------------------
    def kpis(self, source: str, filters: dict) -> dict:
        df, full = self.frame(source, filters), self.frame(source)
        y = df[TARGET]
        signals = self.risk_signals(source, filters, limit=1)
        by_class = df.groupby(TARGET)[list(INDEX_FEATURES)].mean().round(2)
        return {
            "rows": int(len(df)),
            "rows_total": int(len(full)),
            "drop_count": int(y.sum()),
            "drop_share": _share(int(y.sum()), len(df)),
            "drop_share_total": _share(int(full[TARGET].sum()), len(full)),
            "synthetic_share": _share(int(df["is_synthetic"].sum()), len(df)),
            "top_risk_signal": signals["risk"][0] if signals["risk"] else None,
            "index_means": {
                name: {CLASS_LABELS[int(c)]: float(by_class.loc[c, name]) for c in by_class.index}
                for name in INDEX_FEATURES
            },
        }

    def breakdown(self, feature: str, source: str, filters: dict) -> dict:
        """Drop share for each answer to one question, with lift vs the filtered overall share."""
        if feature not in ALL_FEATURES:
            raise ValueError(f"Unknown feature '{feature}'.")
        f, df = ALL_FEATURES[feature], self.frame(source, filters)
        overall = _share(int(df[TARGET].sum()), len(df))
        g = df.groupby(feature)[TARGET].agg(["size", "sum"])
        rows = []
        for code, label in f.answers.items():
            n, d = (int(g.loc[code, "size"]), int(g.loc[code, "sum"])) if code in g.index else (0, 0)
            if n == 0 and feature in INDEX_FEATURES:
                continue  # don't list empty index values
            share = _share(d, n)
            rows.append({"code": code, "label": label, "n": n, "drop": d, "drop_share": share,
                         "pct_of_rows": _share(n, len(df)),
                         "lift": round(share / overall, 3) if share is not None and overall else None})
        return {"feature": feature, "title": f.title, "group": f.group, "description": f.description,
                "overall_drop_share": overall, "rows_total": int(len(df)), "answers": rows}

    def breakdowns(self, group: str, source: str, filters: dict) -> list[dict]:
        names = [n for n, f in ALL_FEATURES.items() if f.group == group]
        if not names:
            raise ValueError(f"Unknown group '{group}'.")
        return [self.breakdown(n, source, filters) for n in names]

    def profile(self, feature: str, source: str, filters: dict) -> dict:
        """How the answer distribution differs between drop and no-drop students."""
        f, df = ALL_FEATURES[feature], self.frame(source, filters)
        series = []
        for c, label in CLASS_LABELS.items():
            sub = df[df[TARGET] == c][feature]
            dist = sub.value_counts(normalize=True)
            series.append({"class": label, "n": int(len(sub)), "mean": round(float(sub.mean()), 3) if len(sub) else None,
                           "shares": [round(float(dist.get(code, 0.0)), 4) for code in f.answers]})
        present = df[feature].unique()
        keep = [i for i, code in enumerate(f.answers) if feature not in INDEX_FEATURES or code in present]
        return {"feature": feature, "title": f.title, "description": f.description,
                "labels": [list(f.answers.values())[i] for i in keep],
                "series": [{**s, "shares": [s["shares"][i] for i in keep]} for s in series]}

    def crosstab(self, row: str, col: str, source: str, filters: dict) -> dict:
        fr, fc, df = ALL_FEATURES[row], ALL_FEATURES[col], self.frame(source, filters)
        g = df.groupby([row, col])[TARGET].agg(["size", "sum"])
        rows_present = [c for c in fr.answers if c in df[row].unique()]
        cols_present = [c for c in fc.answers if c in df[col].unique()]
        share, n = [], []
        for r in rows_present:
            share.append([_share(int(g.loc[(r, c), "sum"]), int(g.loc[(r, c), "size"]))
                          if (r, c) in g.index else None for c in cols_present])
            n.append([int(g.loc[(r, c), "size"]) if (r, c) in g.index else 0 for c in cols_present])
        return {"row": row, "col": col, "row_title": fr.title, "col_title": fc.title,
                "row_labels": [fr.label(c) for c in rows_present],
                "col_labels": [fc.label(c) for c in cols_present], "drop_share": share, "n": n}

    def tools(self, source: str, filters: dict) -> dict:
        df = self.frame(source, filters)
        out = []
        for name in TOOL_FEATURES:
            adopters = df[df[name] == 1]
            out.append({
                "feature": name, "title": ALL_FEATURES[name].title.removeprefix("Uses "),
                "adoption": {CLASS_LABELS[c]: _share(int((df[df[TARGET] == c][name] == 1).sum()),
                                                     int((df[TARGET] == c).sum())) for c in CLASS_LABELS},
                "users": int(len(adopters)),
                "drop_share_among_users": _share(int(adopters[TARGET].sum()), len(adopters)),
            })
        return {"tools": out}

    def risk_signals(self, source: str, filters: dict, limit: int | None = None,
                     min_n: int | None = None) -> dict:
        """Every (question, answer) pair ranked by lift = drop share among respondents giving that
        answer / overall drop share. Answers given by fewer than `min_n` respondents are skipped."""
        df = self.frame(source, filters)
        min_n = self.dcfg["min_group_size"] if min_n is None else min_n
        overall = df[TARGET].mean() if len(df) else 0
        rows = []
        for name, f in BASE_FEATURES.items():
            if name in filters:
                continue  # a filtered feature has a single value: no contrast to report
            g = df.groupby(name)[TARGET].agg(["size", "mean"])
            for code, (n, share) in g.iterrows():
                if n < min_n or overall == 0:
                    continue
                rows.append({"feature": name, "question": f.title, "group": f.group, "code": int(code),
                             "answer": f.label(code), "n": int(n), "drop_share": round(float(share), 4),
                             "lift": round(float(share / overall), 3), "actionable": f.actionable})
        risk = sorted([r for r in rows if r["lift"] > 1], key=lambda r: -r["lift"])
        protective = sorted([r for r in rows if r["lift"] < 1], key=lambda r: r["lift"])
        if limit:
            risk, protective = risk[:limit], protective[:limit]
        return {"overall_drop_share": round(float(overall), 4), "min_n": min_n,
                "risk": risk, "protective": protective}

    # --- group scorecards -----------------------------------------------------------------------
    # (id, label, feature, value counted as "yes")
    SCORECARD_METRICS = [
        ("dropout_rate", "Dropout rate", None, None),
        ("ai_always", "Uses AI for study always", "ai_study_frequency", 4),
        ("over_reliant", "Relies on AI over own thinking", "over_reliance", 2),
        ("negative_analytical", "Says AI hurts analytical skills", "analytical_skills_effect", 0),
        ("reduced_motivation", "Says AI reduces motivation", "motivation_effect", 0),
        ("full_ai_project", "Submitted a full AI project", "submitted_full_project", 1),
        ("ai_in_exam", "Used AI in an in-class exam", "used_ai_in_exam", 1),
        ("flagged", "Flagged by a professor", "flagged_by_professor", 1),
        ("always_reviews", "Always reviews AI content", "reviews_content", 2),
        ("learned_prompting", "Has learned prompt writing", "learned_prompting", 1),
        ("ai_improved_education", "Says AI improved education", "ai_improved_education", 2),
    ]

    def scorecard(self, feature: str, source: str, filters: dict) -> dict:
        """Key indicators (share of students) for every answer group of one question. Groups smaller
        than `min_group_size` are left out (listed in `hidden_groups`): their rates would be noise."""
        f, df = ALL_FEATURES[feature], self.frame(source, filters)
        min_n = self.dcfg["min_group_size"]
        sizes = {c: int((df[feature] == c).sum()) for c in f.answers}
        groups = [c for c in f.answers if sizes[c] >= min_n]
        hidden = [{"label": f.label(c), "n": sizes[c]} for c in f.answers if 0 < sizes[c] < min_n]
        rows = []
        for mid, label, col, yes in self.SCORECARD_METRICS:
            values = []
            for c in groups:
                sub = df[df[feature] == c]
                hit = sub[TARGET] == 1 if col is None else sub[col] == yes
                values.append(round(float(hit.mean()), 4))
            rows.append({"id": mid, "label": label, "values": values})
        return {"feature": feature, "title": f.title, "min_n": min_n, "hidden_groups": hidden,
                "groups": [{"code": c, "label": f.label(c), "n": sizes[c]} for c in groups],
                "metrics": rows}

    # --- synthetic data quality ------------------------------------------------------------------
    def data_quality(self) -> dict:
        aug = self.frames["augmented"]
        real, syn = aug[aug["is_synthetic"] == 0], aug[aug["is_synthetic"] == 1]
        base = list(BASE_FEATURES)
        rows = []
        for name in base:
            p = real[name].value_counts(normalize=True)
            q = syn[name].value_counts(normalize=True)
            tvd = 0.5 * float(p.reindex(p.index.union(q.index), fill_value=0)
                              .sub(q.reindex(p.index.union(q.index), fill_value=0)).abs().sum())
            rows.append({"feature": name, "title": BASE_FEATURES[name].title, "tvd": round(tvd, 4),
                         "answers_real": int(real[name].nunique()), "answers_synthetic": int(syn[name].nunique())})
        rows.sort(key=lambda r: -r["tvd"])
        counts = {src: {CLASS_LABELS[c]: int((self.frames[src][TARGET] == c).sum()) for c in CLASS_LABELS}
                  for src in ("original", "augmented", "synthetic")}
        counts["real training rows"] = {CLASS_LABELS[c]: int((real[TARGET] == c).sum()) for c in CLASS_LABELS}
        return {
            "rows_real": int(len(real)), "rows_synthetic": int(len(syn)),
            "distinct_synthetic": int(len(syn[base + [TARGET]].drop_duplicates())),
            "duplicate_share": _share(int(len(syn) - len(syn[base + [TARGET]].drop_duplicates())), len(syn)),
            "features_losing_answers": sum(r["answers_synthetic"] < r["answers_real"] for r in rows),
            "class_counts": counts, "features": rows,
        }

    def compare_distribution(self, feature: str) -> dict:
        """Answer shares for one question: real training rows vs synthetic rows."""
        f, aug = ALL_FEATURES[feature], self.frames["augmented"]
        out = {"feature": feature, "title": f.title, "labels": list(f.answers.values()), "series": []}
        for flag, label in ((0, "Real"), (1, "Synthetic")):
            dist = aug[aug["is_synthetic"] == flag][feature].value_counts(normalize=True)
            out["series"].append({"name": label, "shares": [round(float(dist.get(c, 0.0)), 4) for c in f.answers]})
        return out

    # --- model -----------------------------------------------------------------------------------
    @cached_property
    def best(self) -> dict:
        path = self.outputs / "best_model.joblib"
        if not path.exists():
            raise NotReadyError("No trained model found. Run `uv run dropout-risk` first.")
        return joblib.load(path)

    def _band(self, p: float) -> str:
        b = self.dcfg["risk_bands"]
        return "high" if p >= b["high"] else "medium" if p >= b["medium"] else "low"

    def _proba(self, X: pd.DataFrame) -> np.ndarray:
        return self.best["pipeline"].predict_proba(X[self.best["base_features"]])[:, 1]

    @cached_property
    def scored_original(self) -> pd.DataFrame:
        df = self.frames["original"].copy()
        df["probability"] = self._proba(df)
        df["band"] = df["probability"].map(self._band)
        df["in_training"] = df["respondent_id"].isin(self.train_ids)
        return df

    def watchlist(self, filters: dict, limit: int | None = None, band: str | None = None) -> dict:
        """Original respondents ranked by predicted drop probability, with the risk signals they show."""
        df = self.scored_original
        for feat, codes in filters.items():
            df = df[df[feat].isin(codes)]
        lifts = {(r["feature"], r["code"]): r for r in self.risk_signals("original", {})["risk"]}
        band_counts = {b: int((df["band"] == b).sum()) for b in BANDS}
        if band:
            df = df[df["band"] == band]
        df = df.sort_values("probability", ascending=False).head(limit or self.dcfg["watchlist_size"])
        students = []
        for _, r in df.iterrows():
            present = sorted((lifts[(f, int(r[f]))] for f in BASE_FEATURES if (f, int(r[f])) in lifts),
                             key=lambda s: -s["lift"])
            students.append({
                "respondent_id": int(r["respondent_id"]), "probability": round(float(r["probability"]), 4),
                "band": r["band"], "recorded_drop": int(r[TARGET]), "in_training": bool(r["in_training"]),
                "major": BASE_FEATURES["major"].label(r["major"]),
                "study_year": BASE_FEATURES["study_year"].label(r["study_year"]),
                "gender": BASE_FEATURES["is_male"].label(r["is_male"]),
                "university": BASE_FEATURES["is_private_university"].label(r["is_private_university"]),
                "signals": [f"{s['question']}: {s['answer']}" for s in present[:3]],
            })
        return {"rows": int(sum(band_counts.values())), "band_counts": band_counts,
                "risk_bands": self.dcfg["risk_bands"], "students": students}

    def _risk_score(self, X: pd.DataFrame) -> np.ndarray:
        """Monotone risk score (log-odds). Unlike the probability it doesn't saturate at 0/1, so it
        still ranks changes for students the model is already certain about."""
        pipe, X = self.best["pipeline"], X[self.best["base_features"]]
        if hasattr(pipe, "decision_function"):
            return pipe.decision_function(X)
        p = np.clip(pipe.predict_proba(X)[:, 1], 1e-9, 1 - 1e-9)
        return np.log(p / (1 - p))

    @cached_property
    def safest_answers(self) -> dict[str, int]:
        """For each actionable question, the answer with the lowest observed drop share."""
        orig, out = self.frames["original"], {}
        for f, feat in BASE_FEATURES.items():
            if feat.actionable:
                shares = orig.groupby(f)[TARGET].agg(["size", "mean"])
                shares = shares[shares["size"] >= self.dcfg["min_group_size"]]
                if not shares.empty:
                    out[f] = int(shares["mean"].idxmin())
        return out

    def predict(self, answers: dict[str, int], max_steps: int = 6) -> dict:
        """Score one student. Missing answers default to the most common answer in the survey.

        `what_would_reduce_risk` is a greedy action plan: each step applies the single actionable
        change (to that question's lowest-risk answer) that lowers the model's risk score most,
        on top of the previous steps. `probability_if_changed` is cumulative."""
        orig = self.frames["original"]
        row = {f: int(orig[f].mode().iloc[0]) for f in BASE_FEATURES}
        for f, code in answers.items():
            if f not in BASE_FEATURES:
                raise ValueError(f"Unknown question '{f}'.")
            if int(code) not in BASE_FEATURES[f].answers:
                raise ValueError(f"Invalid answer {code} for '{f}'. Valid: {list(BASE_FEATURES[f].answers)}.")
            row[f] = int(code)
        p = float(self._proba(pd.DataFrame([row]))[0])

        plan, current = [], dict(row)
        score = float(self._risk_score(pd.DataFrame([current]))[0])
        prob = p
        for _ in range(max_steps):
            options = [f for f, safe in self.safest_answers.items() if current[f] != safe]
            if not options:
                break
            trials = pd.DataFrame([{**current, f: self.safest_answers[f]} for f in options])
            scores = self._risk_score(trials)
            i = int(np.argmin(scores))
            if scores[i] >= score - 1e-6:
                break  # no remaining change lowers the risk score
            f, feat = options[i], BASE_FEATURES[options[i]]
            new_prob = float(self._proba(trials.iloc[[i]])[0])
            plan.append({"feature": f, "question": feat.title, "current": feat.label(current[f]),
                         "suggested": feat.label(self.safest_answers[f]),
                         "probability_if_changed": round(new_prob, 4), "reduction": round(prob - new_prob, 4)})
            current[f], score, prob = self.safest_answers[f], float(scores[i]), new_prob
            if self._band(prob) == "low" and prob < 0.05:
                break
        return {"probability": round(p, 4), "band": self._band(p), "risk_bands": self.dcfg["risk_bands"],
                "answers_used": row, "model": self.best["model"], "what_would_reduce_risk": plan}

    @cached_property
    def performance(self) -> dict:
        res_path = self.outputs / "model_results.csv"
        if not res_path.exists():
            raise NotReadyError("No model results found. Run `uv run dropout-risk` first.")
        res = pd.read_csv(res_path)
        test = pd.read_csv(self.processed / "test_real.csv", index_col="row_id")
        X_test, y_test = test.drop(columns=[TARGET]), test[TARGET]
        metrics = ["f1", "roc_auc", "average_precision", "recall", "precision", "accuracy", "balanced_accuracy"]
        models = []
        for _, r in res.iterrows():
            ci = [float(x) for x in re.findall(r"\d+\.\d+(?:e-?\d+)?", str(r.get("test_f1_ci", "")))][:2]
            entry = {"model": r["model"], "label": r["label"], "best_params": r["best_params"],
                     "cv": {m: round(float(r[f"cv_{m}"]), 4) for m in metrics},
                     "cv_std": {m: round(float(r[f"cv_{m}_std"]), 4) for m in metrics},
                     "test": {m: round(float(r[f"test_{m}"]), 4) for m in metrics},
                     "test_f1_ci": ci}
            path = self.outputs / "models" / f"{r['model']}.joblib"
            if path.exists():
                proba = joblib.load(path).predict_proba(X_test)[:, 1]
                fpr, tpr, _ = roc_curve(y_test, proba)
                entry["roc"] = {"fpr": np.round(fpr, 4).tolist(), "tpr": np.round(tpr, 4).tolist(),
                                "auc": round(float(roc_auc_score(y_test, proba)), 4)}
                entry["confusion"] = confusion_matrix(y_test, (proba >= 0.5).astype(int), labels=[0, 1]).tolist()
            models.append(entry)
        return {"best_model": self.best["model"], "selected_features": self.best["selected_features"],
                "test_rows": int(len(test)), "test_drop": int(y_test.sum()),
                "baseline_f1_always_drop": round(2 * y_test.mean() / (1 + y_test.mean()), 4),
                "models": models}

    def importance(self) -> dict:
        imp_path, sel_path = self.outputs / "permutation_importance.csv", self.outputs / "feature_selection.csv"
        if not imp_path.exists():
            raise NotReadyError("No importance results found. Run `uv run dropout-risk` first.")
        imp = pd.read_csv(imp_path)
        sel = pd.read_csv(sel_path)
        title = lambda n: ALL_FEATURES[n].title if n in ALL_FEATURES else n.replace("_", " ")
        return {
            "model": self.best["model"],
            "permutation": [{"feature": r.feature, "title": title(r.feature),
                             "mean": round(float(r.mean), 5), "std": round(float(r.std), 5)}
                            for r in imp.itertuples()],
            "selection": [{"feature": r.feature, "title": title(r.feature),
                           "score": None if pd.isna(r.score) else round(float(r.score), 4),
                           "status": r.status} for r in sel.itertuples()],
        }

    # --- export ----------------------------------------------------------------------------------
    def dataset(self, source: str, filters: dict, decoded: bool) -> pd.DataFrame:
        df = self.frame(source, filters).copy()
        if decoded:
            for name, f in ALL_FEATURES.items():
                if name in df and name in BASE_FEATURES:
                    df[name] = df[name].map(f.label)
            df[TARGET] = df[TARGET].map(CLASS_LABELS)
        return df
