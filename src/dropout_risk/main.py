"""Run the pipeline: split -> feature selection -> five tuned models -> evaluation -> best model.

    uv run dropout-risk
"""

import argparse
import json
import time
import warnings
from pathlib import Path

import joblib
import pandas as pd
from sklearn.inspection import permutation_importance

from . import evaluation as ev
from .config import load_config
from .data import load_dataset, split
from .features import engineer_features, select_features
from .models import MODELS, SCORING, tune


def _md_table(df: pd.DataFrame, floatfmt: str = "{:.3f}") -> str:
    cells = [[floatfmt.format(v) if isinstance(v, float) else str(v) for v in row]
             for row in df.itertuples(index=False)]
    lines = ["| " + " | ".join(map(str, df.columns)) + " |", "|" + "---|" * len(df.columns)]
    return "\n".join(lines + ["| " + " | ".join(r) + " |" for r in cells])


def pick_best(results: pd.DataFrame, metric: str) -> str:
    """Highest CV primary metric; near-ties (3 dp) broken by CV ROC-AUC, then by simplicity."""
    ranked = results.assign(_p=results[f"cv_{metric}"].round(3), _a=results["cv_roc_auc"].round(3))
    ranked = ranked.sort_values(["_p", "_a", "complexity"], ascending=[False, False, True])
    return ranked["model"].iloc[0]


def run(cfg: dict) -> dict:
    out = Path(cfg["output_dir"])
    (out / "figures").mkdir(parents=True, exist_ok=True)
    (out / "models").mkdir(parents=True, exist_ok=True)
    metric, seed = cfg["training"]["primary_metric"], cfg["random_state"]

    X, y = load_dataset(cfg)
    X_train, X_test, y_train, y_test = split(X, y, cfg)
    print(f"{X_train.shape[1]} base features | train {len(X_train)} rows ({int(y_train.sum())} drop) | "
          f"test {len(X_test)} rows ({int(y_test.sum())} drop)")

    selected, sel_report = select_features(engineer_features(X_train), y_train, cfg)
    sel_report.to_csv(out / "feature_selection.csv", index_label="feature")
    ev.plot_feature_selection(sel_report, out / "figures" / "feature_selection.png")
    print(f"selected {len(selected)} features: {selected}")

    rows, curves, cms, fitted = [], {}, {}, {}
    for spec in MODELS:
        t0 = time.perf_counter()
        search = tune(spec, cfg, selected, X_train, y_train)
        i, cvr = search.best_index_, search.cv_results_
        proba = search.predict_proba(X_test)[:, 1]
        row = {"model": spec.name, "label": spec.label, "complexity": spec.complexity}
        for m in SCORING:
            row[f"cv_{m}"] = cvr[f"mean_test_{m}"][i]
            row[f"cv_{m}_std"] = cvr[f"std_test_{m}"][i]
        row |= {f"test_{k}": v for k, v in ev.test_metrics(y_test, proba).items()}
        row |= {f"test_{k}": v for k, v in ev.bootstrap_ci(
            y_test, proba, n=cfg["training"]["bootstrap_samples"], seed=seed).items()}
        row["best_params"] = json.dumps({k.removeprefix("model__"): v for k, v in search.best_params_.items()},
                                        default=str)
        row["fit_seconds"] = round(time.perf_counter() - t0, 1)
        rows.append(row)
        curves[spec.name], cms[spec.name] = (y_test.to_numpy(), proba), ev.confusion(y_test, proba)
        fitted[spec.name] = search.best_estimator_
        joblib.dump(search.best_estimator_, out / "models" / f"{spec.name}.joblib")
        print(f"  {spec.label:<20} CV {metric} {row[f'cv_{metric}']:.3f}±{row[f'cv_{metric}_std']:.3f} | "
              f"test {metric} {row[f'test_{metric}']:.3f}  AUC {row['test_roc_auc']:.3f}  "
              f"({row['fit_seconds']}s)")

    results = pd.DataFrame(rows)
    best = pick_best(results, metric)
    labels = dict(zip(results["model"], results["label"]))
    results.to_csv(out / "model_results.csv", index=False)
    joblib.dump({"pipeline": fitted[best], "model": best, "selected_features": selected,
                 "base_features": list(X_train.columns)}, out / "best_model.joblib")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        imp = permutation_importance(fitted[best], X_test, y_test, scoring="roc_auc",
                                     n_repeats=30, random_state=seed)
    imp_df = (pd.DataFrame({"mean": imp.importances_mean, "std": imp.importances_std}, index=X_test.columns)
              .sort_values("mean", ascending=False))
    imp_df.to_csv(out / "permutation_importance.csv", index_label="feature")

    baseline = ev.test_metrics(y_test, [1.0] * len(y_test))  # always predict "drop"
    ev.plot_model_comparison(results, metric, best, out / "figures" / "model_comparison.png",
                             baseline=baseline[metric])
    ev.plot_curves(curves, labels, best, out / "figures" / "roc_pr_curves.png")
    ev.plot_confusion_matrices(cms, labels, best, out / "figures" / "confusion_matrices.png")
    ev.plot_permutation_importance(imp_df, f"Which survey answers drive {labels[best]}? (test set)",
                                   out / "figures" / "permutation_importance.png")
    _write_report(cfg, results, best, selected, sel_report, imp_df, X_train, X_test,
                  y_train, y_test, baseline, out)
    print(f"  -> best: {labels[best]}  (outputs in {out})")
    return results.loc[results["model"] == best].iloc[0].to_dict()


def _write_report(cfg, results, best, selected, sel_report, imp_df,
                  X_train, X_test, y_train, y_test, baseline, out):
    metric = cfg["training"]["primary_metric"]
    table = results.sort_values(f"cv_{metric}", ascending=False)
    cv_cols = pd.DataFrame({
        "Model": table["label"] + table["model"].map(lambda m: " ★" if m == best else ""),
        f"CV {metric}": [f"{a:.3f} ± {b:.3f}" for a, b in zip(table[f"cv_{metric}"], table[f"cv_{metric}_std"])],
        "CV ROC-AUC": [f"{a:.3f} ± {b:.3f}" for a, b in zip(table["cv_roc_auc"], table["cv_roc_auc_std"])],
        f"Test {metric} (95% CI)": [f"{v:.3f} ({lo:.2f}–{hi:.2f})" for v, (lo, hi)
                                    in zip(table[f"test_{metric}"], table[f"test_{metric}_ci"])],
        "Test ROC-AUC": table["test_roc_auc"].round(3),
        "Test recall": table["test_recall"].round(3),
        "Test precision": table["test_precision"].round(3),
        "Test accuracy": table["test_accuracy"].round(3),
    })
    b = results.set_index("model").loc[best]
    sel = sel_report.loc[selected, ["mutual_info", "rf_importance", "score"]].reset_index(names="feature")
    text = f"""# Dropout risk — model report

- Base features: {X_train.shape[1]} survey answers → {len(sel_report)} after feature engineering → **{len(selected)} selected**
- Train: {len(X_train)} respondents ({int(y_train.sum())} drop), oversampled with SMOTEN to
  {cfg['smote']['samples_per_class']} per class inside every CV fold and for the final fit
- Test: {len(X_test)} held-out respondents, never resampled ({int(y_test.sum())} drop)
- Tuning: random search, {cfg['training']['n_iter']} candidates/model, {cfg['training']['cv_splits']}-fold CV
  × {cfg['training']['cv_repeats']} repeats; selection by CV {metric} (test set not used for selection)

## Best model: {b['label']}

CV {metric} **{b[f'cv_{metric}']:.3f} ± {b[f'cv_{metric}_std']:.3f}**, test {metric} **{b[f'test_{metric}']:.3f}**
(95% CI {b[f'test_{metric}_ci'][0]:.2f}–{b[f'test_{metric}_ci'][1]:.2f}), test ROC-AUC {b['test_roc_auc']:.3f}.
Hyper-parameters: `{b['best_params']}`

## All models

{_md_table(cv_cols)}

Trivial baseline on the same test set, always predicting "drop": {metric} {baseline[metric]:.3f},
recall 1.000, precision {baseline['precision']:.3f}, ROC-AUC 0.500. A model that doesn't beat this
has learned nothing useful.

![model comparison](figures/model_comparison.png)
![roc and pr curves](figures/roc_pr_curves.png)
![confusion matrices](figures/confusion_matrices.png)

## Selected features

{_md_table(sel)}

![feature selection](figures/feature_selection.png)

## What drives the best model (permutation importance on the test set)

{_md_table(imp_df.head(10).reset_index(names="survey answer"))}

![permutation importance](figures/permutation_importance.png)
"""
    (out / "report.md").write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Train and evaluate dropout-risk models.")
    parser.add_argument("--config", default=None, help="path to config YAML")
    args = parser.parse_args(argv)

    run(load_config(args.config))


if __name__ == "__main__":
    main()
